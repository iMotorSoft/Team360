"""Phase 2 tests for canonical extraction verification.

Defect 1: Volume canonicalization differs by language
Defect 2: human_approval None is ambiguous
Defect 3: Partial corrections destroy unrelated entity-source relationships

No network calls. No DB. No LLM.
"""

from __future__ import annotations

import pytest

from modules.sales_diagnosis_runtime.canonical_patterns import (
    extract_approval,
    extract_volume,
    extract_entities,
    extract_systems,
    is_correction,
)
from modules.sales_diagnosis_runtime.runtime import AssistantConversationRuntime
from modules.sales_diagnosis_runtime import (
    AssistantTurnInput,
    ConversationState,
    InMemoryStateRepository,
)


# ═══════════════════════════════════════════════════════════════════════
# PART 1: Volume canonicalization
# ═══════════════════════════════════════════════════════════════════════

class TestVolumeCanonicalization:
    """Verify that volume canonical structure is identical across es/en/he."""

    @pytest.mark.parametrize("msg,expected_period", [
        ("80 por día",           "day"),
        ("80 per day",           "day"),
        ("80 ביום",              "day"),
        ("60 por semana",        "week"),
        ("60 per week",          "week"),
        ("60 בשבוע",             "week"),
        ("100 por mes",          "month"),
        ("100 per month",        "month"),
        ("100 בחודש",            "month"),
    ])
    def test_period_canonical(self, msg: str, expected_period: str) -> None:
        result = extract_volume(msg)
        assert result is not None, f"No volume extracted from {msg!r}"
        assert result["period"] == expected_period, (
            f"period={result['period']} != {expected_period} for {msg!r}"
        )
        # Also verify language-independent value
        assert result["value"] in (60, 80, 100)

    def test_approximate_spanish(self) -> None:
        r = extract_volume("unas 80 por día")
        assert r is not None
        assert r["value"] == 80

    def test_approximate_english(self) -> None:
        r = extract_volume("around 80 per day")
        assert r is not None
        assert r["value"] == 80

    def test_approximate_hebrew(self) -> None:
        r = extract_volume("כ-80 ביום")
        assert r is not None
        assert r["value"] == 80

    @pytest.mark.parametrize("msg,expected_value,expected_entity", [
        ("80 consultas por día",   80, "consulta"),
        ("80 inquiries per day",   80, "inquirie"),
        ("80 פניות ביום",          80, None),
        ("40 pedidos por mes",     40, "pedido"),
        ("40 orders per month",    40, "order"),
        ("40 הזמנות בחודש",        40, None),
    ])
    def test_unit_variation(self, msg: str, expected_value: int, expected_entity: str | None) -> None:
        """Note: unit currently depends on language. This is a known limitation."""
        result = extract_volume(msg)
        assert result is not None
        assert result["value"] == expected_value
        # Unit may differ by language — this is the defect we need to fix
        if expected_entity:
            assert result.get("unit") == expected_entity, (
                f"unit={result.get('unit')} != {expected_entity} for {msg!r}"
            )

    def test_es_en_he_period_identity(self) -> None:
        """Same fact across languages must produce identical volume dict."""
        es = extract_volume("80 por día")
        en = extract_volume("80 per day")
        he = extract_volume("80 ביום")

        assert es is not None and en is not None and he is not None
        # Value must match
        assert es["value"] == en["value"] == he["value"] == 80
        # Period MUST be identical (this is the defect: currently es="día", en="day")
        assert es["period"] == en["period"] == he["period"], (
            f"Periods differ: es={es['period']} en={en['period']} he={he['period']}"
        )

    def test_volume_same_semantic_memory_across_languages(self) -> None:
        """Integration test: volume extraction feeds into semantic_memory the same way."""
        runtime = AssistantConversationRuntime()

        def _extract_volume_via_runtime(msg: str) -> dict | None:
            repo = InMemoryStateRepository()
            rt = AssistantConversationRuntime(state_repository=repo)
            input_ = AssistantTurnInput(
                session_id="vol-test",
                assistant_instance_code="team360_sales_diagnosis",
                package_code="pkg_sales_diagnosis",
                knowledge_scope_code="ks_test",
                user_message=msg,
            )
            output = rt.handle_turn(input_)
            mem = (output.next_state or ConversationState(
                session_id="", assistant_instance_code="", package_code="",
                knowledge_scope_code="")).semantic_memory
            return mem.get("volume")

        es_vol = _extract_volume_via_runtime("80 por día")
        en_vol = _extract_volume_via_runtime("80 per day")
        he_vol = _extract_volume_via_runtime("80 ביום")

        assert es_vol is not None
        assert en_vol is not None
        assert he_vol is not None

        # This should be identical across languages
        assert es_vol["value"] == en_vol["value"] == he_vol["value"] == 80
        # Period must be canonical
        assert es_vol["period"] == en_vol["period"] == he_vol["period"] == "day", (
            f"Volume period differs: es={es_vol['period']} en={en_vol['period']} he={he_vol['period']}"
        )


# ═══════════════════════════════════════════════════════════════════════
# PART 2: Human approval states
# ═══════════════════════════════════════════════════════════════════════

class TestHumanApprovalStates:
    """Verify that human_approval states are unambiguous and distinguish
    required/conditional/not_required/unknown."""

    @pytest.mark.parametrize("msg,expected", [
        # Spanish required
        ("Todo debe ser aprobado por una persona",          "required"),
        ("Todo debe ser aprobado por una persona.",         "required"),
        # English required
        ("Everything requires human approval",              "required"),
        # Hebrew required
        ("הכול דורש אישור אנושי",                           "required"),
    ])
    def test_required(self, msg: str, expected: str) -> None:
        result = extract_approval(msg)
        assert result == expected, f"extract_approval({msg!r}) = {result!r}, expected {expected!r}"

    @pytest.mark.parametrize("msg,expected", [
        ("Las respuestas comunes salen solas, pero los descuentos requieren aprobación",
         "conditional"),
        ("Common replies are automatic, but discounts require approval",
         "conditional"),
        ("תשובות רגילות אוטומטיות, אבל הנחות דורשות אישור",
         "conditional"),
    ])
    def test_conditional(self, msg: str, expected: str) -> None:
        result = extract_approval(msg)
        assert result == expected, f"extract_approval({msg!r}) = {result!r}, expected {expected!r}"

    @pytest.mark.parametrize("msg,expected", [
        # Spanish — negative statements should be not_required
        ("No requiere aprobación humana",                   "not_required"),
        ("No requiere aprobación humana.",                  "not_required"),
        ("No necesita revisión",                            "not_required"),
        # English
        ("No human approval is required",                   "not_required"),
        ("Does not need review",                            "not_required"),
        # Hebrew
        ("לא נדרש אישור אנושי",                              "not_required"),
        ("לא צריך בדיקה",                                    "not_required"),
    ])
    def test_not_required(self, msg: str, expected: str) -> None:
        result = extract_approval(msg)
        assert result == expected, f"extract_approval({msg!r}) = {result!r}, expected {expected!r}"

    @pytest.mark.parametrize("msg", [
        # Messages WITHOUT approval information — must NOT set human_approval
        "Recibimos consultas por WhatsApp",
        "We receive inquiries through WhatsApp",
        "אנחנו מקבלים פניות דרך WhatsApp",
        "80 por día",
        "El stock está en el sistema",
    ])
    def test_unknown_does_not_set_human_approval(self, msg: str) -> None:
        """Messages without approval info should not set human_approval
        (None return means 'no info' which the runtime should interpret
        as 'leave existing value unchanged')."""
        result = extract_approval(msg)
        assert result is None, (
            f"extract_approval({msg!r}) = {result!r}, expected None "
            f"(no approval info = don't change existing value)"
        )


# ═══════════════════════════════════════════════════════════════════════
# PART 3: Partial corrections — entity-source relationships
# ═══════════════════════════════════════════════════════════════════════

class TestPartialCorrections:
    """Verify that correcting one entity's source does not destroy
    relationships for other entities."""

    def _turn(self, runtime, session_id, msg):
        return runtime.handle_turn(AssistantTurnInput(
            session_id=session_id,
            assistant_instance_code="team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_test",
            user_message=msg,
        ))

    def test_spanish_partial_correction_preserves_erp(self) -> None:
        """Correcting prices from spreadsheet to CRM must preserve
        inventory → ERP."""
        repo = InMemoryStateRepository()
        runtime = AssistantConversationRuntime(state_repository=repo)

        # Turn 1: Establish inventory→ERP, prices→spreadsheet
        self._turn(runtime, "ent-source",
                   "El stock está en el ERP y los precios en una planilla.")
        state = repo.load("ent-source")
        mem = state.semantic_memory if state else {}

        # After turn 1, we should have both systems
        assert "erp" in mem.get("systems_and_data_sources", []), (
            f"ERP not in systems after turn 1: {mem.get('systems_and_data_sources')}"
        )
        assert "Planilla / Excel" in mem.get("systems_and_data_sources", []), (
            f"Planilla / Excel not in systems after turn 1"
        )

        # Turn 2: Correct prices → CRM (not spreadsheet)
        self._turn(runtime, "ent-source",
                   "Los precios ya no están en la planilla, están en el CRM.")
        state2 = repo.load("ent-source")
        mem2 = state2.semantic_memory if state2 else {}

        # DEFECT: After turn 2, the correction currently replaces ALL systems
        systems2 = mem2.get("systems_and_data_sources", [])
        assert "erp" in systems2, (
            f"ERP LOST after correction! systems_and_data_sources = {systems2} "
            f"— prices correction should not erase inventory source"
        )
        assert "crm" in systems2, (
            f"CRM not added: {systems2}"
        )

    def test_english_partial_correction_preserves_erp(self) -> None:
        """Same test in English."""
        repo = InMemoryStateRepository()
        runtime = AssistantConversationRuntime(state_repository=repo)

        self._turn(runtime, "ent-source-en",
                   "Inventory is in the ERP and prices are in a spreadsheet.")
        state = repo.load("ent-source-en")
        mem = state.semantic_memory if state else {}

        self._turn(runtime, "ent-source-en",
                   "Prices are no longer in the spreadsheet; they are in the CRM.")
        state2 = repo.load("ent-source-en")
        mem2 = state2.semantic_memory if state2 else {}

        systems2 = mem2.get("systems_and_data_sources", [])
        assert "erp" in systems2, (
            f"ERP LOST in English correction! systems = {systems2}"
        )
        assert "crm" in systems2, (
            f"CRM not in systems: {systems2}"
        )

    def test_hebrew_partial_correction_preserves_erp(self) -> None:
        """Same test in Hebrew."""
        repo = InMemoryStateRepository()
        runtime = AssistantConversationRuntime(state_repository=repo)

        self._turn(runtime, "ent-source-he",
                   "המלאי נמצא ב-ERP והמחירים בגיליון אלקטרוני.")
        state = repo.load("ent-source-he")
        mem = state.semantic_memory if state else {}

        self._turn(runtime, "ent-source-he",
                   "המחירים כבר לא בגיליון, הם נמצאים ב-CRM.")
        state2 = repo.load("ent-source-he")
        mem2 = state2.semantic_memory if state2 else {}

        systems2 = mem2.get("systems_and_data_sources", [])
        assert "erp" in systems2, (
            f"ERP LOST in Hebrew correction! systems = {systems2}"
        )
        assert "crm" in systems2, (
            f"CRM not in systems: {systems2}"
        )

    def test_correction_does_not_lose_volume(self) -> None:
        """Correction about systems should not eliminate previously set volume."""
        repo = InMemoryStateRepository()
        runtime = AssistantConversationRuntime(state_repository=repo)

        self._turn(runtime, "ent-vol", "Son unas 80 consultas por día.")
        state1 = repo.load("ent-vol")
        mem1 = state1.semantic_memory if state1 else {}
        assert "volume" in mem1 and mem1["volume"]["value"] == 80

        self._turn(runtime, "ent-vol",
                   "Los precios ya no están en la planilla, están en el CRM.")
        state2 = repo.load("ent-vol")
        mem2 = state2.semantic_memory if state2 else {}
        # Volume should still be present
        assert "volume" in mem2, (
            "Volume was lost after correction!"
        )
        assert mem2["volume"]["value"] == 80

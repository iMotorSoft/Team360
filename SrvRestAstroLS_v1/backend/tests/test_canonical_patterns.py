"""Tests for canonical multilingual semantic extraction.

Covers es/en/he for: channels, systems, entities, approval, volume, corrections.
No network calls. No DB. No LLM.
"""

from __future__ import annotations

import pytest

from modules.sales_diagnosis_runtime.canonical_patterns import (
    extract_approval,
    extract_channels,
    extract_entities,
    extract_systems,
    extract_volume,
    is_business_context,
    is_correction,
)


# ═══════════════════════════════════════════════════════════════════════
# 1. CHANNELS — es/en/he
# ═══════════════════════════════════════════════════════════════════════

class TestExtractChannels:
    @pytest.mark.parametrize("msg,expected", [
        # Spanish
        ("whatsapp", ["whatsapp"]),
        ("WhatsApp", ["whatsapp"]),
        ("gmail", ["gmail"]),
        ("correo", ["email"]),
        ("correo electrónico", ["email"]),
        ("Facebook", ["facebook"]),
        ("Instagram", ["instagram"]),
        ("sitio web", ["web"]),
        ("teléfono", ["phone"]),
        ("chat", ["chat"]),
        ("página web", ["web"]),
        # English
        ("email", ["email"]),
        ("e-mail", ["email"]),
        ("website", ["web"]),
        ("phone", ["phone"]),
        # Hebrew
        ("וואטסאפ", ["whatsapp"]),
        ("ג׳ימייל", ["gmail"]),
        ("אימייל", ["email"]),
        ("דואר אלקטרוני", ["email"]),
        ("אתר", ["web"]),
        ("טלפון", ["phone"]),
        # Multiple in one message
        ("WhatsApp y Gmail", ["whatsapp", "gmail"]),
        ("WhatsApp and Gmail", ["whatsapp", "gmail"]),
        ("WhatsApp ו-Gmail", ["whatsapp", "gmail"]),
        ("WhatsApp, Gmail y correo", ["whatsapp", "gmail", "email"]),
        # No channels
        ("quiero automatizar ventas", []),
        ("80 por día", []),
    ])
    def test_extract_channels(self, msg: str, expected: list[str]) -> None:
        result = extract_channels(msg)
        assert sorted(result) == sorted(expected), (
            f"extract_channels({msg!r}) = {result}, expected {expected}"
        )


# ═══════════════════════════════════════════════════════════════════════
# 2. SYSTEMS — es/en/he
# ═══════════════════════════════════════════════════════════════════════

class TestExtractSystems:
    @pytest.mark.parametrize("msg,expected", [
        # Spanish
        ("ERP", ["erp"]),
        ("CRM", ["crm"]),
        ("planilla", ["spreadsheet"]),
        ("excel", ["spreadsheet"]),
        ("hoja de cálculo", ["spreadsheet"]),
        ("base de datos", ["database"]),
        ("bd", ["database"]),
        ("programa cerrado de Windows", ["closed_windows_application"]),
        ("software propietario", ["proprietary_system"]),
        # English
        ("spreadsheet", ["spreadsheet"]),
        ("Google Sheet", ["spreadsheet"]),
        ("database", ["database"]),
        ("inventory system", ["inventory_system"]),
        ("closed Windows application", ["closed_windows_application"]),
        ("proprietary software", ["proprietary_system"]),
        # Hebrew
        ("אקסל", ["spreadsheet"]),
        ("גיליון", ["spreadsheet"]),
        ("מסד נתונים", ["database"]),
        ("מערכת מלאי", ["inventory_system"]),
        ("תוכנת Windows סגורה", ["closed_windows_application"]),
        ("תוכנה קניינית", ["proprietary_system"]),
        # Multiple in one message
        ("ERP y planilla", ["erp", "spreadsheet"]),
        ("ERP and spreadsheet", ["erp", "spreadsheet"]),
        # No systems
        ("quiero automatizar ventas", []),
    ])
    def test_extract_systems(self, msg: str, expected: list[str]) -> None:
        result = extract_systems(msg)
        assert sorted(result) == sorted(expected), (
            f"extract_systems({msg!r}) = {result}, expected {expected}"
        )


# ═══════════════════════════════════════════════════════════════════════
# 3. ENTITIES — es/en/he
# ═══════════════════════════════════════════════════════════════════════

class TestExtractEntities:
    @pytest.mark.parametrize("msg,expected", [
        # Spanish
        ("stock", ["inventory"]),
        ("inventario", ["inventory"]),
        ("precios", ["prices"]),
        ("precio", ["prices"]),
        ("clientes", ["customers"]),
        ("descuentos", ["discounts"]),
        ("reclamos", ["claims"]),
        ("pedidos", ["orders"]),
        ("documentos", ["documents"]),
        ("consultas de venta", ["sales_inquiries"]),
        # English
        ("inventory", ["inventory"]),
        ("prices", ["prices"]),
        ("customers", ["customers"]),
        ("discounts", ["discounts"]),
        ("claims", ["claims"]),
        ("orders", ["orders"]),
        ("documents", ["documents"]),
        ("sales inquiries", ["sales_inquiries"]),
        # Hebrew
        ("מלאי", ["inventory"]),
        ("מחירים", ["prices"]),
        ("לקוחות", ["customers"]),
        ("הנחות", ["discounts"]),
        ("תביעות", ["claims"]),
        ("הזמנות", ["orders"]),
        ("מסמכים", ["documents"]),
        ("פניות מכירה", ["sales_inquiries"]),
        # Multiple
        ("stock y precios", ["inventory", "prices"]),
        ("inventory and prices", ["inventory", "prices"]),
        # No entities
        ("hola", []),
    ])
    def test_extract_entities(self, msg: str, expected: list[str]) -> None:
        result = extract_entities(msg)
        assert sorted(result) == sorted(expected), (
            f"extract_entities({msg!r}) = {result}, expected {expected}"
        )


# ═══════════════════════════════════════════════════════════════════════
# 4. APPROVAL — es/en/he
# ═══════════════════════════════════════════════════════════════════════

class TestExtractApproval:
    @pytest.mark.parametrize("msg,expected", [
        # Spanish
        ("requiere aprobación", "required"),
        ("lo revisa un supervisor", "required"),
        ("autorización necesaria", "required"),
        ("aprobación de un gerente", "required"),
        ("persona revisa", "required"),
        # English
        ("manager approval", "required"),
        ("human review", "required"),
        ("requires approval", "required"),
        ("needs review", "required"),
        # Hebrew
        ("אישור מנהל", "required"),
        ("בדיקה אנושית", "required"),
        ("נדרשת בדיקה", "required"),
        # Conditional (common + but + discounts + approval)
        ("las respuestas comunes pueden salir solas, pero los descuentos especiales los revisa una persona",
         "conditional"),
        ("common replies are automatic, but special discounts require manager approval",
         "conditional"),
        # No approval
        ("quiero automatizar ventas", None),
        ("80 por día", None),
    ])
    def test_extract_approval(self, msg: str, expected: str | None) -> None:
        result = extract_approval(msg)
        assert result == expected, (
            f"extract_approval({msg!r}) = {result!r}, expected {expected!r}"
        )


# ═══════════════════════════════════════════════════════════════════════
# 5. VOLUME — es/en/he
# ═══════════════════════════════════════════════════════════════════════

class TestExtractVolume:
    def _check(self, msg: str, value: int | float, period_like: str, unit: str | None = None) -> None:
        result = extract_volume(msg)
        assert result is not None, f"extract_volume({msg!r}) returned None"
        assert result["value"] == value, f"value: {result['value']} != {value}"
        assert period_like in result["period"], f"period: {result['period']} doesn't match {period_like}"
        if unit:
            assert result["unit"] == unit, f"unit: {result['unit']} != {unit}"

    def test_spanish(self) -> None:
        self._check("80 por día", 80, "día")
        self._check("100 consultas diarias", 100, "dia", "consulta")
        self._check("60 al mes", 60, "mes")

    def test_english(self) -> None:
        self._check("80 per day", 80, "day")
        self._check("around 100 inquiries daily", 100, "daily", "inquirie")
        self._check("60 per month", 60, "month")

    def test_hebrew(self) -> None:
        self._check("80 ביום", 80, "יום")
        self._check("כ-100 פניות ביום", 100, "יום")

    @pytest.mark.parametrize("msg", [
        "hola",
        "quiero automatizar",
        "sistema",
        "",
    ])
    def test_no_volume(self, msg: str) -> None:
        assert extract_volume(msg) is None


# ═══════════════════════════════════════════════════════════════════════
# 6. CORRECTIONS — es/en/he
# ═══════════════════════════════════════════════════════════════════════

class TestIsCorrection:
    @pytest.mark.parametrize("msg,expected", [
        # Spanish
        ("en realidad son 120", True),
        ("mejor dicho, usamos ERP", True),
        ("rectifico los datos", True),
        # English
        ("actually, it's 120", True),
        ("correction: we use ERP", True),
        ("i meant 120, not 80", True),
        ("let me correct that", True),
        # Hebrew
        ("בעצם 120", True),
        ("אני מתקן", True),
        # No correction
        ("quiero automatizar ventas", False),
        ("80 por día", False),
        ("hola", False),
    ])
    def test_is_correction(self, msg: str, expected: bool) -> None:
        assert is_correction(msg) == expected


# ═══════════════════════════════════════════════════════════════════════
# 7. BUSINESS CONTEXT
# ═══════════════════════════════════════════════════════════════════════

class TestIsBusinessContext:
    def test_spanish(self) -> None:
        assert is_business_context("mi negocio es de repuestos") is not None
        assert is_business_context("mi empresa se dedica a ventas") is not None
        assert is_business_context("hola") is None

    def test_english(self) -> None:
        assert is_business_context("my business is selling parts") is not None
        assert is_business_context("my company sells products") is not None
        assert is_business_context("hi") is None

    def test_hebrew(self) -> None:
        assert is_business_context("העסק שלי מוכר חלקים") is not None
        assert is_business_context("החברה עוסקת במכירות") is not None


# ═══════════════════════════════════════════════════════════════════════
# 8. CANONICAL EQUIVALENCE — same concept across languages
# ═══════════════════════════════════════════════════════════════════════

class TestCanonicalEquivalence:
    """Verify that es/en/he produce the same canonical extraction for
    equivalent messages."""

    SPANISH_MSGS = [
        "Entran por WhatsApp y Gmail",
        "El stock está en el ERP y los precios en una planilla",
        "Los descuentos requieren aprobación de un gerente",
    ]
    ENGLISH_MSGS = [
        "They come through WhatsApp and Gmail",
        "Inventory is in the ERP and prices are in a spreadsheet",
        "Discounts require manager approval",
    ]
    HEBREW_MSGS = [
        "הפניות מגיעות דרך WhatsApp ו-Gmail",
        "המלאי נמצא במערכת ERP והמחירים בגיליון אלקטרוני",
        "הנחות דורשות אישור מנהל",
    ]

    def test_channels_equivalent(self) -> None:
        es = extract_channels(self.SPANISH_MSGS[0])
        en = extract_channels(self.ENGLISH_MSGS[0])
        he = extract_channels(self.HEBREW_MSGS[0])
        assert sorted(es) == sorted(en) == sorted(he), (
            f"channels not equivalent: es={es} en={en} he={he}"
        )
        assert "whatsapp" in es and "gmail" in es

    def test_systems_equivalent(self) -> None:
        es = extract_systems(self.SPANISH_MSGS[1])
        en = extract_systems(self.ENGLISH_MSGS[1])
        he = extract_systems(self.HEBREW_MSGS[1])
        assert sorted(es) == sorted(en) == sorted(he), (
            f"systems not equivalent: es={es} en={en} he={he}"
        )
        assert "erp" in es and "spreadsheet" in es

    def test_entities_equivalent(self) -> None:
        es = extract_entities(self.SPANISH_MSGS[1])
        en = extract_entities(self.ENGLISH_MSGS[1])
        he = extract_entities(self.HEBREW_MSGS[1])
        assert sorted(es) == sorted(en) == sorted(he), (
            f"entities not equivalent: es={es} en={en} he={he}"
        )
        assert "inventory" in es and "prices" in es

    def test_approval_equivalent(self) -> None:
        es = extract_approval(self.SPANISH_MSGS[2])
        en = extract_approval(self.ENGLISH_MSGS[2])
        he = extract_approval(self.HEBREW_MSGS[2])
        assert es == en == he == "required", (
            f"approval not equivalent: es={es} en={en} he={he}"
        )

    def test_full_dialogue_semantic_state_equivalent(self) -> None:
        """Simulate semantic_memory accumulation across all three languages."""
        from modules.sales_diagnosis_runtime.runtime import AssistantConversationRuntime
        from modules.sales_diagnosis_runtime import AssistantConversationRuntime as Runtime

        # Build three states from equivalent dialogues
        messages = {
            "es": self.SPANISH_MSGS,
            "en": self.ENGLISH_MSGS,
            "he": self.HEBREW_MSGS,
        }

        # Actually just test that extraction functions are equivalent
        for lang, msgs in messages.items():
            all_channels: list[str] = []
            all_systems: list[str] = []
            all_entities: list[str] = []
            for msg in msgs:
                all_channels.extend(extract_channels(msg))
                all_systems.extend(extract_systems(msg))
                all_entities.extend(extract_entities(msg))

            # Deduplicate
            channels = list(dict.fromkeys(all_channels))
            systems = list(dict.fromkeys(all_systems))
            entities = list(dict.fromkeys(all_entities))

            if lang == "es":
                es_state = {"channels": channels, "systems": systems, "entities": entities}
            elif lang == "en":
                en_state = {"channels": channels, "systems": systems, "entities": entities}
            else:
                he_state = {"channels": channels, "systems": systems, "entities": entities}

        assert sorted(es_state["channels"]) == sorted(en_state["channels"]) == sorted(he_state["channels"])
        assert sorted(es_state["systems"]) == sorted(en_state["systems"]) == sorted(he_state["systems"])
        assert sorted(es_state["entities"]) == sorted(en_state["entities"]) == sorted(he_state["entities"])

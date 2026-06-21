"""Tests for semantic clause extraction and classification.

Validates that channel/system extraction correctly handles negation,
temporal references, hypotheticals, questions, corrections, and mixed clauses.
"""

from __future__ import annotations

import pytest
from modules.sales_diagnosis_runtime.canonical_patterns import (
    split_semantic_clauses,
    classify_clause,
    extract_current_channels,
    extract_current_systems,
    extract_channels,
    extract_systems,
)


# ── split_semantic_clauses ─────────────────────────────────────────────────


class TestSplitSemanticClauses:
    def test_simple_message(self):
        assert split_semantic_clauses("Usamos email.") == ["Usamos email."]

    def test_contrast_with_comma(self):
        clauses = split_semantic_clauses("No tenemos CRM, usamos sistema propio.")
        assert len(clauses) == 2
        assert "No tenemos CRM" in clauses[0]
        assert "sistema propio" in clauses[1]

    def test_temporal_contrast(self):
        clauses = split_semantic_clauses("Antes usábamos WhatsApp, ahora email.")
        assert len(clauses) >= 2
        assert "Antes" in clauses[0]
        assert "email" in clauses[-1]

    def test_question_and_assertion(self):
        clauses = split_semantic_clauses("¿Se puede usar WhatsApp? Hoy usamos email.")
        assert len(clauses) >= 2
        assert "Hoy" in clauses[-1]

    def test_future_and_present(self):
        clauses = split_semantic_clauses("Queremos CRM en el futuro; actualmente usamos planilla.")
        assert len(clauses) >= 2

    def test_contrast_pero(self):
        clauses = split_semantic_clauses("No usamos email para ventas, pero sí para soporte.")
        assert len(clauses) >= 2

    def test_multichannel_single_clause(self):
        clauses = split_semantic_clauses("Hoy usamos email y WhatsApp.")
        assert len(clauses) == 1

    def test_double_negation_then_assertion(self):
        clauses = split_semantic_clauses("No tenemos CRM ni planilla; usamos un sistema propio.")
        assert len(clauses) >= 2

    def test_correction(self):
        clauses = split_semantic_clauses("Dije WhatsApp, pero en realidad es email.")
        assert len(clauses) >= 2


# ── classify_clause ────────────────────────────────────────────────────────


class TestClassifyClause:
    @pytest.mark.parametrize("clause", [
        "usamos email",
        "hoy usamos email",
        "actualmente usamos planilla",
        "las consultas llegan por WhatsApp",
        "usamos un sistema propio",
        "solo usamos email",
        "ahora usamos email",
    ])
    def test_current(self, clause):
        assert classify_clause(clause) == "current"

    @pytest.mark.parametrize("clause", [
        "no usamos WhatsApp",
        "no tenemos CRM",
        "nunca usamos email",
        "ya no usamos planilla",
        "todavía no tenemos sistema propio",
        "ahora mismo no usamos CRM",
        "sin usar CRM",
    ])
    def test_negated(self, clause):
        assert classify_clause(clause) == "negated"

    @pytest.mark.parametrize("clause", [
        "antes usábamos WhatsApp",
        "usábamos CRM el año pasado",
        "solíamos trabajar con planillas",
    ])
    def test_past(self, clause):
        assert classify_clause(clause) == "past"

    @pytest.mark.parametrize("clause", [
        "en el futuro queremos CRM",
        "más adelante usaremos WhatsApp",
        "queremos implementar un sistema propio",
    ])
    def test_future(self, clause):
        assert classify_clause(clause) == "future"

    @pytest.mark.parametrize("clause", [
        "si usáramos WhatsApp",
        "tal vez usemos CRM",
        "por ejemplo podríamos usar planilla",
        "quizás usemos email",
    ])
    def test_hypothetical(self, clause):
        assert classify_clause(clause) == "hypothetical"

    @pytest.mark.parametrize("clause", [
        "¿se puede usar WhatsApp?",
        "¿necesitamos CRM?",
        "¿conviene usar email?",
    ])
    def test_question(self, clause):
        assert classify_clause(clause) == "question"


# ── extract_current_channels ───────────────────────────────────────────────


class TestExtractCurrentChannels:
    @pytest.mark.parametrize("message,expected", [
        ("Usamos email.", ["email"]),
        ("Recibimos mails.", ["email"]),
        ("Nos escriben por correo.", ["email"]),
        ("Las consultas llegan por WhatsApp.", ["whatsapp"]),
        ("Hoy usamos email y WhatsApp.", ["email", "whatsapp"]),
        ("Las consultas llegan por web.", ["web"]),
        ("No usamos WhatsApp.", []),
        ("No recibimos mails.", []),
        ("Nunca usamos email.", []),
        ("No usamos WhatsApp, usamos email.", ["email"]),
        ("Antes usábamos WhatsApp, ahora email.", ["email"]),
        ("¿Se puede usar WhatsApp? Hoy usamos email.", ["email"]),
        ("Queremos WhatsApp en el futuro; hoy usamos email.", ["email"]),
        ("Recibimos consultas por email y WhatsApp.", ["email", "whatsapp"]),
        ("Dije WhatsApp, pero en realidad es email.", ["email"]),
        ("No, no es WhatsApp: es email.", ["email"]),
    ])
    def test_channels(self, message, expected):
        result = sorted(extract_current_channels(message))
        assert result == sorted(expected), f"Failed for {message!r}: got {result}"


# ── extract_current_systems ────────────────────────────────────────────────


class TestExtractCurrentSystems:
    @pytest.mark.parametrize("message,expected", [
        ("Usamos CRM.", ["crm"]),
        ("Trabajamos con una planilla.", ["spreadsheet"]),
        ("Tenemos un sistema propio.", ["custom_system"]),
        ("No tenemos CRM.", []),
        ("No usamos planilla.", []),
        ("Nunca usamos sistema propio.", []),
        ("No tenemos CRM, usamos sistema propio.", ["custom_system"]),
        ("Queremos CRM en el futuro; actualmente usamos planilla.", ["spreadsheet"]),
        ("Usábamos CRM el año pasado; hoy usamos sistema propio.", ["custom_system"]),
        ("¿Necesitamos CRM? Actualmente usamos sistema propio.", ["custom_system"]),
        ("No tenemos CRM ni planilla; usamos sistema propio.", ["custom_system"]),
        ("Antes dije CRM, pero usamos sistema propio.", ["custom_system"]),
        ("No, me equivoqué: no usamos planilla, usamos CRM.", ["crm"]),
    ])
    def test_systems(self, message, expected):
        result = sorted(extract_current_systems(message))
        assert result == sorted(expected), f"Failed for {message!r}: got {result}"


# ── Regression: whole-message extraction still works ──────────────────────


class TestWholeMessageExtraction:
    def test_extract_channels_positive(self):
        assert "email" in extract_channels("Usamos email y WhatsApp")

    def test_extract_systems_positive(self):
        assert "crm" in extract_systems("Tenemos CRM")


# ── Canonicalization ──────────────────────────────────────────────────────


class TestCanonicalization:
    @pytest.mark.parametrize("message,canonical_channel", [
        ("mail", "email"),
        ("mails", "email"),
        ("email", "email"),
        ("emails", "email"),
        ("e-mail", "email"),
        ("correo", "email"),
        ("correo electronico", "email"),
    ])
    def test_email_variants(self, message, canonical_channel):
        result = extract_current_channels(message)
        assert canonical_channel in result, f"{message!r} should map to {canonical_channel}"

    @pytest.mark.parametrize("message,canonical_system", [
        ("planilla", "spreadsheet"),
        ("excel", "spreadsheet"),
        ("sistema propio", "custom_system"),
    ])
    def test_system_variants(self, message, canonical_system):
        result = extract_current_systems(message)
        assert canonical_system in result, f"{message!r} should map to {canonical_system}"

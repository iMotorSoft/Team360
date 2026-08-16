"""Deterministic canonical category normalization tests for Flow routing.

These tests lock the contract between the intake model output and the
deterministic sector resolver. No model or database is involved.
"""

from __future__ import annotations

import pytest

from modules.flow.domain.routing import (
    CANONICAL_CATEGORIES,
    normalize_routing_category,
    resolve_sector_id,
)
from modules.flow.intake.ai import _SYSTEM_PROMPT


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        # canonical value -> canonical value
        ("alumbrado", "alumbrado"),
        # known safe synonyms -> canonical
        ("alumbrado_publico", "alumbrado"),
        ("luminaria", "alumbrado"),
        ("poste_de_luz", "alumbrado"),
        ("street_lighting", "alumbrado"),
        # compound safe labels that lead with a catalog label -> canonical
        ("Alumbrado público - luminaria apagada", "alumbrado"),
        ("Alumbrado público / luminaria apagada", "alumbrado"),
        ("luminaria apagada en la cuadra", "alumbrado"),
        ("Reparación de alumbrado público - poste de luz", "alumbrado"),
    ],
)
def test_resolve_sector_id_resolves_known_and_compound_labels(value, expected):
    assert resolve_sector_id(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        # unknown category -> unresolved
        "arbolado",
        "pozo",
        "vereda rota",
        # ambiguous / out-of-catalog -> unresolved (leading token not in catalog)
        "robo de luminaria",
        "Emergencias - Riesgo eléctrico / poste caído",
        "denuncia por ruidos molestos",
    ],
)
def test_resolve_sector_id_leaves_unknown_and_ambiguous_unresolved(value):
    assert resolve_sector_id(value) is None


@pytest.mark.parametrize("value", [None, "", "   ", "___"])
def test_resolve_sector_id_empty_or_null_is_unresolved(value):
    assert resolve_sector_id(value) is None


@pytest.mark.parametrize(
    "value",
    ["ALUMBRADO", "Luminaria", "  Alumbrado Público  ", "Alumbrado  público"],
)
def test_resolve_sector_id_handles_case_and_whitespace(value):
    assert resolve_sector_id(value) == "alumbrado"


def test_normalize_routing_category_strips_accents_case_and_punctuation():
    assert normalize_routing_category("Alumbrado Público") == "alumbrado_publico"
    assert normalize_routing_category("  Poste de Luz !! ") == "poste_de_luz"
    assert normalize_routing_category(None) == ""
    assert normalize_routing_category("") == ""


def test_canonical_categories_is_closed_and_used_by_prompt():
    assert CANONICAL_CATEGORIES == ("alumbrado",)
    assert '"alumbrado"' in _SYSTEM_PROMPT
    assert "vocabulario cerrado" in _SYSTEM_PROMPT

"""Unit tests for the executive case domain (pure formatting)."""
from __future__ import annotations

import unittest

from modules.telchi.investigation.validation.executive.executive_domain import (
    ExecutiveCase, action_for, confidence_label, flag_labels,
)


class TestMappings(unittest.TestCase):
    def test_action_for(self):
        self.assertIn("acelerar", action_for("BUY_NOW"))
        self.assertIn("No comprar", action_for("DO_NOT_BUY"))
        self.assertEqual(action_for("UNKNOWN_DECISION"), "UNKNOWN_DECISION")

    def test_confidence_label(self):
        self.assertEqual(confidence_label("HIGH"), "ALTA")
        self.assertEqual(confidence_label("LOW"), "BAJA")
        self.assertEqual(confidence_label("XYZ"), "XYZ")

    def test_flag_labels(self):
        self.assertEqual(flag_labels(["IMPORT_DELAY_RISK"]),
                         ["riesgo de demora en importación"])
        self.assertEqual(flag_labels(["SOME_FLAG"]), ["SOME_FLAG"])


class TestExecutiveCase(unittest.TestCase):
    def _case(self):
        return ExecutiveCase(
            title="FRASCO X",
            what_happens="Se agota el frasco antes de fin de temporada.",
            why_matters="Afecta 6 productos.",
            have_physical="10.000",
            have_equivalent="2.000",
            have_open="5.000",
            need_future="20.000",
            can_produce="3.000",
            open_order="5.000",
            open_state="EN TRÁNSITO NO CONFIRMADO",
            lead_time="110 días",
            risk_when="2026-11",
            action="Comprar / acelerar de inmediato",
            confidence="ALTA",
            flags=["PRODUCTION_BLOCKED"],
        )

    def test_to_markdown_contains_all_answers(self):
        md = self._case().to_markdown()
        for token in ("Por qué importa", "Cuánto tenemos", "Cuánto necesitamos",
                      "Cuánto podemos producir", "Cuándo aparece el riesgo",
                      "Acción recomendada", "Confianza del análisis"):
            self.assertIn(token, md)

    def test_to_dict_keys(self):
        d = self._case().to_dict()
        for key in ("title", "what_happens", "have_physical", "action", "confidence"):
            self.assertIn(key, d)


if __name__ == "__main__":
    unittest.main()

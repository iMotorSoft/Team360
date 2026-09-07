"""Tests unitarios puros — normalización de fuentes comerciales (sin HANA)."""
from __future__ import annotations

import sys
import unittest


from modules.telchi.investigation.datalake.commercial_opportunities import sources  # noqa: E402
from modules.telchi.investigation.datalake.commercial_opportunities.classifier import (  # noqa: E402
    CAUSES, Classification, EVIDENCE_EXACT,
)


class TestItemCorrection(unittest.TestCase):
    def test_l01094_is_acido_nitrico(self):
        # Evidencia OITM: L01094 = ACIDO NITRICO. nombre zinc => corrección.
        code, reason = sources.correct_item_code("l01094", "Sulfato de Zinc Feed x 25 kg")
        self.assertEqual(code, "L01794")
        self.assertIsNotNone(reason)

    def test_normal_code_untouched(self):
        code, reason = sources.correct_item_code("L01794", "SULFATO DE ZINC FEED GRADE")
        self.assertEqual(code, "L01794")
        self.assertIsNone(reason)

    def test_missing_code(self):
        code, reason = sources.correct_item_code("", "ALGO")
        self.assertEqual(code, "")
        self.assertEqual(reason, "CODIGO_FALTANTE")


class TestNormalizationPure(unittest.TestCase):
    def test_reason_normalization(self):
        self.assertEqual(sources._norm_reason(" PRECIOS "), "PRECIO")
        self.assertEqual(sources._norm_reason("STOCK"), "STOCK")
        self.assertEqual(sources._norm_reason(None), "")

    def test_float_parse(self):
        self.assertEqual(sources._to_float("2,5"), 2.5)
        self.assertEqual(sources._to_float("75.0"), 75.0)
        self.assertIsNone(sources._to_float("abc"))

    def test_date_parse(self):
        from datetime import datetime
        self.assertEqual(sources._to_date(datetime(2026, 5, 14, 0, 0)).isoformat(), "2026-05-14")
        self.assertIsNone(sources._to_date(None))

    def test_total_computed(self):
        o = sources.Opportunity(
            source="t", source_sheet="s", source_row=1, date=None, channel_raw="C",
            item_code_raw="L01794", item_code_report="L01794", product_raw="ZINC",
            qty=450.0, unit="KG", price=26.5, total_raw=11925.0,
            declared_reason="STOCK", salesperson_raw="X", comment="", customer_raw="",
        )
        self.assertEqual(o.total_computed, 11925.0)

    def test_causes_taxonomy(self):
        self.assertIn("LOST_LOGISTICS_DELAY", CAUSES)
        self.assertIn("LOST_STOCK_OTHER_LOCATION", CAUSES)
        self.assertIn("SOLD_LATER", CAUSES)


if __name__ == "__main__":
    unittest.main(verbosity=2)
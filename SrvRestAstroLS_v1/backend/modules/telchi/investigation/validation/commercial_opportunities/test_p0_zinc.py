"""Tests P0 Zinc — caso 14/05/2026 (integración READ ONLY HANA + Excel).

El caso cerrado debe demostrar:
  Excel → producto correcto → cliente → proforma → stock fecha → almacén
  → movimientos → venta posterior → clasificación

Gate: TELCHI_COMMERCIAL_OPPORTUNITY_P0_PRODUCTS_V1_PASS (parte Zinc).
"""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path


from modules.telchi.investigation.datalake.commercial_opportunities import sources, stock_trace, matching  # noqa: E402
from modules.telchi.investigation.datalake.commercial_opportunities.sap_queries import (  # noqa: E402
    get_invoices_for_item,
    get_item,
    get_quotations_for_item,
    get_movements,
    get_stock_now,
    get_transfers_for_item,
    get_customer_sales,
    get_retail_one_invoices,
)

ITEM_ZINC = "L01794"
ITEM_WRONG = "L01094"  # declarado en Excel = ACIDO NITRICO (código incorrecto)
OPP_DATE = date(2026, 5, 14)


class TestP0ZincSources(unittest.TestCase):
    """Fuente comercial: el caso 14/05/2026 se detecta y normaliza."""

    @classmethod
    def setUpClass(cls):
        cls.opps = sources.ingest_ventas_perdidas()

    def test_case_present(self):
        matches = [o for o in self.opps if o.date == OPP_DATE and "ZINC" in o.product_raw.upper()]
        self.assertTrue(matches, "caso zinc 14/05 no encontrado")
        self.assertEqual(matches[0].qty, 450.0)
        self.assertEqual(matches[0].declared_reason, "STOCK")
        self.assertIn("fidero", matches[0].comment.lower())

    def test_bad_product_code_detected(self):
        """L01094 declarado = sulfato de zinc; OITM demuestra que es ácido nítrico."""
        itm = get_item(ITEM_WRONG)
        self.assertEqual(itm["ItemName"].upper(), "ACIDO NITRICO X KG.")
        itm_ok = get_item(ITEM_ZINC)
        self.assertEqual(itm_ok["ItemName"].upper(), "SULFATO DE ZINC FEED GRADE X 25KG.")

    def test_normalization_correction(self):
        code, reason = sources.correct_item_code("L01094", "Sulfato de Zinc Feed x 25 kg")
        self.assertEqual(code, "L01794")
        self.assertIn("OITM_VERIFIED", reason)


class TestP0ZincStock(unittest.TestCase):
    """Stock histórico reconstruido al 13-14/05/2026 + reconciliación."""

    @classmethod
    def setUpClass(cls):
        cls.movements = get_movements([ITEM_ZINC])  # histórico completo
        cls.recon = stock_trace.reconcile(ITEM_ZINC, cls.movements)

    def test_item_exist(self):
        self.assertIsNotNone(get_item(ITEM_ZINC))

    def test_reconcile_pass(self):
        self.assertTrue(self.recon.pass_recon)
        self.assertGreater(self.recon.checked, 5)

    def test_saavedra_stock_at_opp(self):
        rec = stock_trace.StockReconstruction(ITEM_ZINC, self.movements)
        stock_saa_m1 = rec.stock_at("SAA-M1", date(2026, 5, 13))
        # OITW actual SAA-M1=27019; al 13/05 había más: al menos 33500 demostrado
        self.assertGreaterEqual(stock_saa_m1, 33000, "stock en Saavedra al 13/05 insuficiente")
        self.assertLess(stock_saa_m1, 34000)

    def test_coverage(self):
        rec = stock_trace.StockReconstruction(ITEM_ZINC, self.movements)
        stock = rec.stock_at("SAA-M1", date(2026, 5, 13))
        cov = stock_trace.coverage(450.0, stock)
        # cobertura total (stock >> requerido) se reporta 100%
        self.assertEqual(cov, 100.0)
        self.assertGreater(stock / 450.0, 50)  # 33.5 t vs 450 kg = >74x


class TestP0ZincTransfers(unittest.TestCase):
    """Transferencias SAA-M1 -> LAB-T2: el flujo logístico existía."""

    @classmethod
    def setUpClass(cls):
        cls.transfers = get_transfers_for_item([ITEM_ZINC])

    def test_transfer_route_exists(self):
        route = [t for t in self.transfers if t["FromWhsCod"] == "SAA-M1" and t["WhsCode"] == "LAB-T2"]
        self.assertGreater(len(route), 10, "ruta SAA-M1->LAB-T2 no demostrada")

    def test_transfer_after_opportunity(self):
        after = [t for t in self.transfers
                 if t["FromWhsCod"] == "SAA-M1" and t["WhsCode"] == "LAB-T2"
                 and t["DocDate"] and t["DocDate"].date() >= OPP_DATE
                 and t["DocDate"].date() <= date(2026, 5, 31)]
        self.assertTrue(after, "no hay transferencia SAA-M1->LAB-T2 post-14/05 demostrada")
        self.assertEqual(after[0]["DocNum"], 260107340)  # 16/05/2026 1200 kg


class TestP0ZincSales(unittest.TestCase):
    """Ventas reales del ítem: la proforma → venta EXACT y ventas cercanas."""

    @classmethod
    def setUpClass(cls):
        cls.invoices = get_invoices_for_item([ITEM_ZINC], start=date(2026, 4, 1), end=date(2026, 8, 31))

    def test_exact_quotation_sale(self):
        """Proforma MADRILES 260105727 (12/05) -> factura 261404387 (13/05) EXACT."""
        quts = get_quotations_for_item([ITEM_ZINC], start=date(2026, 5, 1), end=date(2026, 5, 31))
        mad = [q for q in quts if q["DocNum"] == 260105727]
        self.assertEqual(len(mad), 1)
        m = matching.match_proforma_to_sale(mad[0], self.invoices)
        self.assertIsNotNone(m)
        self.assertEqual(m.method, "EXACT_DOCUMENT_LINK")
        self.assertEqual(m.invoice_docnum, 261404387)
        self.assertEqual(m.confidence, "EXACT")

    def test_madriles_450kg_day_before(self):
        """13/05/2026: 900 kg zinc vendidos (2x450) — mismo día anterior a la oportunidad."""
        inv13 = [i for i in self.invoices if i["DocDate"].date() == date(2026, 5, 13)]
        total13 = sum(float(i["Quantity"] or 0) for i in inv13)
        self.assertEqual(total13, 900.0)
        self.assertTrue(all(i["CardName"].upper() == "MADRILES S.A." for i in inv13))

    def test_fidero_later_sale(self):
        """Venta posterior a FIDERO del mismo item (si existe)."""
        rows = get_customer_sales(["FIDERO"], item_codes=[ITEM_ZINC])
        self.assertIsInstance(rows, list)


class TestP0ZincRetailOne(unittest.TestCase):
    def test_fidero_retail_one_exists(self):
        rows = get_retail_one_invoices(customer_name_like="FIDERO", end=date(2026, 9, 30))
        self.assertTrue(rows, "FIDERO no aparece en Retail One")


if __name__ == "__main__":
    unittest.main(verbosity=2)
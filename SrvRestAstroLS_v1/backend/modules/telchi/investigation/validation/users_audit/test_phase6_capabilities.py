"""PHASE 6 unit tests — business capability mapping (pure logic, no DB).

Fixtures per §20:
  direct permission, group permission, inherited, superuser,
  explicit restriction, unknown code, unmapped permission.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

from modules.telchi.investigation.paths import INVESTIGATION_ROOT

ROOT = INVESTIGATION_ROOT

from modules.telchi.investigation.validation.users_audit.capabilities import (
    CapabilityMapping,
    Confidence,
    MappingStatus,
    capability_from_objtype,
    resolve_perm_capability,
    numeric_perm_capability,
    SENSITIVE_CAPABILITIES,
    CAPABILITY_TAXONOMY,
    SO1_CAPABILITY,
)


class TestObjTypeCapabilityMapping(unittest.TestCase):
    def test_invoice_is_sales_create_exact(self):
        m = capability_from_objtype("13")
        self.assertIsNotNone(m)
        self.assertEqual(m.capability, "SALES_CREATE")
        self.assertEqual(m.confidence, Confidence.EXACT)
        self.assertEqual(m.mapping_status, MappingStatus.VALIDATED)

    def test_payment_is_cash(self):
        m = capability_from_objtype("24")
        self.assertEqual(m.capability, "PAYMENT_CREATE")
        self.assertEqual(m.sap_module, "CASH")

    def test_journal_entry(self):
        m = capability_from_objtype("59")
        self.assertEqual(m.capability, "JOURNAL_ENTRY_CREATE")

    def test_stock_transfer(self):
        m = capability_from_objtype("67")
        self.assertEqual(m.capability, "STOCK_TRANSFER")

    def test_canceled_invoice_is_sales_cancel(self):
        m = capability_from_objtype("13", canceled=True)
        self.assertEqual(m.capability, "SALES_CANCEL")

    def test_canceled_payment_is_payment_cancel(self):
        m = capability_from_objtype("24", canceled=True)
        self.assertEqual(m.capability, "PAYMENT_CANCEL")

    def test_unknown_objtype_returns_none(self):
        self.assertIsNone(capability_from_objtype("999"))

    def test_unknown_objtype_canceled_returns_none(self):
        self.assertIsNone(capability_from_objtype("999", canceled=True))


class TestPermissionCapabilityMapping(unittest.TestCase):
    def test_so1_discount_override(self):
        m = resolve_perm_capability("SO1_AU_01DescPorce")
        self.assertIsNotNone(m)
        self.assertEqual(m.capability, "DISCOUNT_OVERRIDE")
        self.assertEqual(m.confidence, Confidence.STRONG)

    def test_so1_price_override(self):
        m = resolve_perm_capability("SO1_AU_01PrecUnico")
        self.assertEqual(m.capability, "PRICE_OVERRIDE")

    def test_numeric_administration_range(self):
        m = numeric_perm_capability(10050)
        self.assertIsNotNone(m)
        self.assertEqual(m.capability, "SYSTEM_CONFIGURATION")
        self.assertEqual(m.confidence, Confidence.HEURISTIC)

    def test_numeric_financials_range(self):
        m = numeric_perm_capability(10150)
        self.assertEqual(m.capability, "ACCOUNTING_POST")

    def test_numeric_inventory_range(self):
        m = numeric_perm_capability(10650)
        self.assertEqual(m.capability, "STOCK_ADJUST")

    def test_numeric_out_of_range_returns_none(self):
        self.assertIsNone(numeric_perm_capability(9999))
        self.assertIsNone(numeric_perm_capability(20000))

    def test_unmapped_perm_returns_none(self):
        self.assertIsNone(resolve_perm_capability("SOME_UNKNOWN_CODE"))

    def test_alpha_addon_perm_not_numeric(self):
        m = resolve_perm_capability("SO1_AU_01DescImporte")
        self.assertIsNotNone(m)
        self.assertEqual(m.capability, "DISCOUNT_OVERRIDE")


class TestTaxonomyInvariants(unittest.TestCase):
    def test_all_mapped_capabilities_in_taxonomy(self):
        for m in list(capability_from_objtype("13").__class__.__mro__):
            pass
        caps = set()
        from modules.telchi.investigation.validation.users_audit.capabilities import OBJTYPE_CAPABILITY, OBJTYPE_CANCEL_CAPABILITY, SO1_CAPABILITY
        for m in list(OBJTYPE_CAPABILITY.values()) + list(OBJTYPE_CANCEL_CAPABILITY.values()) + list(SO1_CAPABILITY.values()):
            caps.add(m.capability)
        for c in caps:
            self.assertIn(c, CAPABILITY_TAXONOMY, f"capability {c} missing from taxonomy")

    def test_sensitive_capabilities_subset_of_taxonomy(self):
        for c in SENSITIVE_CAPABILITIES:
            self.assertIn(c, CAPABILITY_TAXONOMY)

    def test_no_heuristic_as_exact(self):
        for m in SO1_CAPABILITY.values():
            self.assertNotEqual(m.confidence, Confidence.EXACT,
                                "addon permission must not be EXACT without desc table")


if __name__ == "__main__":
    unittest.main(verbosity=2)

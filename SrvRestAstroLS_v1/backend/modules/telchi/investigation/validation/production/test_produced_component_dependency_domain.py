"""Produced component dependency domain unit tests (pure logic)."""
from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

from modules.telchi.investigation.paths import INVESTIGATION_ROOT

ROOT = INVESTIGATION_ROOT

from modules.telchi.investigation.validation.production.produced_component_dependency_domain import (
    ItemRole,
    DependencyEdge,
    derive_graph_depth,
)


class TestItemRole(unittest.TestCase):
    def test_produced_and_intermediate(self):
        r = ItemRole("L05000", True, True, True, True, True, True, True)
        self.assertEqual(r.classification, "PRODUCED_AND_INTERMEDIATE")
        self.assertTrue(r.is_produced_component)

    def test_produced_final_only(self):
        r = ItemRole("L10000", True, True, True, False, False, False, False)
        self.assertEqual(r.classification, "PRODUCED_FINAL_ONLY")

    def test_component_only(self):
        r = ItemRole("M001", False, False, False, True, True, True, False)
        self.assertEqual(r.classification, "COMPONENT_ONLY")

    def test_roles_non_exclusive(self):
        # item can be produced AND component AND sellable simultaneously
        r = ItemRole("L05000", True, True, True, True, True, True, True)
        self.assertTrue(r.has_actual_output)
        self.assertTrue(r.has_actual_component_consumption)
        self.assertTrue(r.is_current_bom_parent)


class TestDependencyEdge(unittest.TestCase):
    def test_edge_aggregation(self):
        e = DependencyEdge("A", "B", 10, 8, Decimal("500"), True, True, 3)
        self.assertEqual(e.historical_order_count, 10)
        self.assertEqual(e.actual_consumption_qty, Decimal("500"))
        self.assertEqual(e.confirmation, "EXACT_DOCUMENT_LINK")


class TestGraphDepth(unittest.TestCase):
    def _edge(self, parent, comp, depth=1):
        return DependencyEdge(parent, comp, 1, 1, Decimal("1"), True, True, 1,
                              dependency_depth=depth)

    def test_simple_depth(self):
        edges = {("A", "B"): self._edge("A", "B"), ("B", "C"): self._edge("B", "C")}
        r = derive_graph_depth(edges, {"B", "C"})
        self.assertEqual(r["per_parent_depth"]["A"], 2)
        self.assertEqual(r["per_parent_depth"]["B"], 1)

    def test_cycle_detection(self):
        edges = {("A", "B"): self._edge("A", "B"), ("B", "A"): self._edge("B", "A")}
        r = derive_graph_depth(edges, {"A", "B"}, max_depth=5)
        self.assertGreaterEqual(r["cycle_hits"], 1)
        # no infinite loop
        self.assertIn("A", r["per_parent_depth"])
        self.assertIn("B", r["per_parent_depth"])

    def test_self_dependency(self):
        edges = {("A", "A"): self._edge("A", "A")}
        r = derive_graph_depth(edges, {"A"}, max_depth=5)
        self.assertEqual(r["self_dependencies"], 1)

    def test_max_depth_guard(self):
        edges = {("A", "B"): self._edge("A", "B"), ("B", "C"): self._edge("B", "C"),
                 ("C", "D"): self._edge("C", "D")}
        r = derive_graph_depth(edges, {"B", "C", "D"}, max_depth=2)
        self.assertLessEqual(r["per_parent_depth"]["A"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
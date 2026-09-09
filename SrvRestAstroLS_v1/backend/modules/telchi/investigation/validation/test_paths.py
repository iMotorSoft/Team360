"""Focused tests for centralized Telchi investigation paths and YAML references."""
from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from modules.telchi.investigation import paths


class TestInvestigationPaths(unittest.TestCase):
    def test_roots_are_absolute_paths(self):
        for root in paths.ROOTS_BY_KEY.values():
            self.assertIsInstance(root, Path)
            self.assertTrue(root.is_absolute())

    def test_external_override_is_absolute_and_cwd_independent(self):
        override = Path("/tmp/telchi-external-files")
        with patch.dict(os.environ, {"TEST_TELCHI_ROOT": str(override)}):
            self.assertEqual(
                paths._external_root("TEST_TELCHI_ROOT", Path("/tmp/unused")),
                override,
            )
        with patch.dict(os.environ, {"TEST_TELCHI_ROOT": "relative/path"}):
            with self.assertRaises(ValueError):
                paths._external_root("TEST_TELCHI_ROOT", Path("/tmp/unused"))

    def test_secret_root_is_independent_from_data_root(self):
        self.assertNotEqual(paths.SECRET_ROOT, paths.DATA_ROOT / "access")
        self.assertEqual(
            paths.HANA_ENV_FILE,
            paths.SECRET_ROOT / "sap" / "hana.env",
        )

    def test_reference_rejects_escape(self):
        with self.assertRaises(ValueError):
            paths.resolve_path_reference(
                {"root_key": "LEGACY_DATA_ROOT", "relative_path": "../outside"}
            )


class TestPathYamlLoaders(unittest.TestCase):
    def test_dataset_inventory_resolves_legacy_root(self):
        inventory = paths.load_path_yaml(
            paths.INVESTIGATION_ROOT / "validation" / "dataset_inventory.yaml"
        )
        self.assertEqual(inventory["generated_from"][1], paths.LEGACY_DATA_ROOT)
        self.assertEqual(inventory["inventory_name"], "telchi_canonical_dataset_inventory")
        self.assertGreater(len(inventory["datasets"]), 10)

    def test_sync_validation_resolves_same_effective_files(self):
        baseline = paths.load_path_yaml(
            paths.INVESTIGATION_ROOT
            / "validation"
            / "legacy_sync"
            / "sync_validation.yaml"
        )
        self.assertEqual(
            baseline["static_source"]["file"],
            paths.LEGACY_DATA_ROOT / "SrvRest" / "srvSyncTelchiSB101.py",
        )
        self.assertEqual(
            baseline["datasets"][0]["warehouse_mapping"]["file"],
            paths.LEGACY_DATA_ROOT / "DS" / "sapWhsOfficeName.xlsx",
        )
        self.assertEqual(baseline["baseline_name"], "telchi_legacy_sync_baseline")


if __name__ == "__main__":
    unittest.main(verbosity=2)

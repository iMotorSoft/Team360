"""Contracts for external Telchi HANA and VPN private configuration paths."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from modules.telchi.investigation import paths


BACKEND_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND_ROOT.parent
SMOKE_PATH = BACKEND_ROOT / "scripts" / "smoke_telchi_sap_hana.py"
VPN_SCRIPTS = (
    APP_ROOT / "scripts" / "telchi" / "fortinet" / "configure.sh",
    APP_ROOT / "scripts" / "telchi" / "fortinet" / "connect-strongswan.sh",
    APP_ROOT / "scripts" / "telchi" / "fortinet" / "validate.sh",
)


def _load_smoke_module():
    spec = importlib.util.spec_from_file_location("telchi_hana_smoke_path_test", SMOKE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hana_tooling_uses_investigation_path_authority() -> None:
    smoke = _load_smoke_module()
    assert smoke.PRIVATE_ENV_FILE == paths.HANA_ENV_FILE
    assert paths.HANA_ENV_FILE == paths.SECRET_ROOT / "sap" / "hana.env"
    assert paths.SECRET_ROOT != paths.DATA_ROOT / "access"


def test_vpn_tooling_requires_external_secret_root() -> None:
    for script in VPN_SCRIPTS:
        source = script.read_text(encoding="utf-8")
        assert "TEAM360_TELCHI_SECRET_ROOT" in source
        assert "TELCHI_DATA_ROOT" not in source
        assert "/access/" not in source
        assert "dataclient/telchi" not in source

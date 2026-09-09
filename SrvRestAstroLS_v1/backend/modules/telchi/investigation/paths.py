"""Stable locations used by the relocated Telchi investigation.

Python and SQL source live in this package. Physical data, evidence and secrets remain external. External roots are
centralized here so investigation modules never depend on the CWD or place
private configuration below the physical Data Root.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def _external_root(environment_name: str, default: Path) -> Path:
    """Return an absolute external root, optionally overridden by environment."""
    configured = Path(os.environ.get(environment_name, str(default))).expanduser()
    if not configured.is_absolute():
        raise ValueError(f"{environment_name} must be an absolute path")
    return configured


INVESTIGATION_ROOT = Path(__file__).resolve().parent
DATA_ROOT = _external_root(
    "TEAM360_TELCHI_DATA_ROOT",
    Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi"),
)
LEGACY_DATA_ROOT = _external_root(
    "TEAM360_TELCHI_LEGACY_ROOT",
    Path("/media/issajar/DEVELOP/Projects/telchi/Insiding/DataScience"),
)
EVIDENCE_ROOT = _external_root(
    "TEAM360_TELCHI_EVIDENCE_ROOT",
    Path(
        "/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/"
        "investigation-consolidation-v1/files/validation"
    ),
)
SECRET_ROOT = _external_root(
    "TEAM360_TELCHI_SECRET_ROOT",
    Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi"),
)
HANA_ENV_FILE = SECRET_ROOT / "sap" / "hana.env"
EXTERNAL_FILES_ROOT = _external_root(
    "TEAM360_TELCHI_EXTERNAL_FILES_ROOT",
    Path("/home/issajar/Downloads"),
)

ROOTS_BY_KEY: Mapping[str, Path] = {
    "INVESTIGATION_ROOT": INVESTIGATION_ROOT,
    "DATA_ROOT": DATA_ROOT,
    "LEGACY_DATA_ROOT": LEGACY_DATA_ROOT,
    "EVIDENCE_ROOT": EVIDENCE_ROOT,
    "SECRET_ROOT": SECRET_ROOT,
    "EXTERNAL_FILES_ROOT": EXTERNAL_FILES_ROOT,
}


def resolve_path_reference(reference: Mapping[str, Any]) -> Path:
    """Resolve a versionable ``root_key``/``relative_path`` path reference."""
    unexpected = set(reference) - {"root_key", "relative_path"}
    if unexpected or "root_key" not in reference:
        raise ValueError("invalid logical path reference")
    root_key = str(reference["root_key"])
    try:
        root = ROOTS_BY_KEY[root_key]
    except KeyError as exc:
        raise ValueError(f"unknown root_key: {root_key}") from exc
    relative = Path(str(reference.get("relative_path", ".")))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("relative_path must stay within its configured root")
    return root / relative


def load_path_yaml(path: Path) -> Any:
    """Load YAML and resolve exact logical path-reference mappings recursively."""
    import yaml

    def resolve(value: Any) -> Any:
        if isinstance(value, dict):
            if set(value) <= {"root_key", "relative_path"} and "root_key" in value:
                return resolve_path_reference(value)
            return {key: resolve(item) for key, item in value.items()}
        if isinstance(value, list):
            return [resolve(item) for item in value]
        return value

    return resolve(yaml.safe_load(path.read_text(encoding="utf-8")))

"""Configuration for the Gupshup WhatsApp adapter.

All values are resolved from environment variables via globalVar.
No secrets are exposed in this module.
"""

from __future__ import annotations

from dataclasses import dataclass

import globalVar


@dataclass(frozen=True)
class GupshupConfig:
    """Resolved Gupshup configuration for a single environment."""

    base_url: str
    api_key: str
    app_name: str
    sender_e164: str
    source_number: str

    @classmethod
    def from_global(cls) -> GupshupConfig:
        """Build configuration from globalVar environment-aware helpers."""
        cfg = globalVar.get_team360_gupshup_config()
        return cls(
            base_url=cfg["base_url"],
            api_key=cfg["api_key"],
            app_name=cfg["app_name"],
            sender_e164=cfg["sender"],
            source_number=cfg["source_number"],
        )

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> GupshupConfig:
        """Build configuration from an explicit dictionary (testing)."""
        return cls(
            base_url=data.get("base_url", "https://api.gupshup.io"),
            api_key=data.get("api_key", ""),
            app_name=data.get("app_name", ""),
            sender_e164=data.get("sender", ""),
            source_number=data.get("source_number", ""),
        )

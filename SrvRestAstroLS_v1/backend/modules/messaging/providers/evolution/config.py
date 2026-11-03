"""DEV-only Evolution configuration from the existing environment convention."""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import os
import re
from urllib.parse import urlparse


class EvolutionConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class EvolutionConfig:
    base_url: str
    instance: str
    api_key: str = field(repr=False)
    timeout: float = 10.0

    @classmethod
    def from_env(cls) -> EvolutionConfig:
        url = os.getenv("TEAM360_EVOLUTION_BASE_URL", "").strip().rstrip("/")
        instance = os.getenv("TEAM360_EVOLUTION_INSTANCE", "").strip()
        key = os.getenv("TEAM360_EVOLUTION_API_KEY", "").strip()
        try:
            timeout = float(os.getenv("TEAM360_EVOLUTION_TIMEOUT_SECONDS", "10"))
        except ValueError:
            raise EvolutionConfigurationError("Invalid Evolution timeout") from None
        parsed = urlparse(url)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or not re.fullmatch(r"[A-Za-z0-9_-]+", instance) or not key
                or not math.isfinite(timeout) or not 0 < timeout <= 30):
            raise EvolutionConfigurationError("Incomplete or invalid Evolution configuration")
        return cls(url, instance, key, timeout)

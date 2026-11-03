"""Only differential Srv05 configuration, resolved explicitly at composition."""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from modules.messaging.settings import MessagingDevSettings
    from modules.messaging.providers.evolution.config import EvolutionConfig


@dataclass(frozen=True)
class Srv05Settings:
    evolution_enabled: bool = False
    provider: str = 'evolution'
    messaging: MessagingDevSettings | None = field(default=None, repr=False)
    evolution: EvolutionConfig | None = field(default=None, repr=False)
    recipient: str = field(default='', repr=False)

    @classmethod
    def from_env(cls) -> Srv05Settings:
        flag = os.getenv('TEAM360_SRV05_EVOLUTION_ENABLED', '0').strip().lower()
        if flag not in {'0', '1', 'false', 'true', 'off', 'on'}:
            raise ValueError('Invalid Srv05 Evolution enable flag')
        if flag in {'0', 'false', 'off'}:
            return cls()
        # Lazy: Srv01 and disabled Srv05 never import Evolution.
        from modules.messaging.settings import MessagingDevSettings
        from modules.messaging.providers.evolution.config import EvolutionConfig
        try:
            if os.getenv('TEAM360_SRV05_MESSAGING_PROVIDER', 'evolution') != 'evolution':
                raise ValueError('Unsupported provider')
            if os.getenv('AUTOMATION_DIAGNOSIS_REPOSITORY') != 'postgres':
                raise ValueError('PostgreSQL lifecycle required')
            return cls(True, 'evolution', MessagingDevSettings.from_env(),
                       EvolutionConfig.from_env(),
                       os.getenv('META_TEAM360_PHONE_NUMBER_ID', '').strip())
        except (ValueError, RuntimeError):
            raise ValueError('Srv05 Evolution configuration invalid; capability not started') from None

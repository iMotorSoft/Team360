"""DEV identity binding, separate from provider credentials and formats."""
from dataclasses import dataclass, field
import os
import re


@dataclass(frozen=True)
class MessagingDevSettings:
    workspace_slug: str
    channel_alias: str
    authorized_sender: str = field(repr=False)
    webhook_token: str = field(repr=False)
    telchi_tenant: str | None = None
    dispatch_mode: str = 'legacy'

    @classmethod
    def from_env(cls):
        if (os.getenv("TEAM360_MESSAGING_DEV_ENABLED") != "1"
                or os.getenv("TEAM360_ENV", "").strip().lower() not in {"development", "dev"}):
            raise ValueError("DEV messaging disabled")
        mode = os.getenv('TEAM360_MESSAGING_DISPATCH_MODE', 'legacy').strip()
        if mode not in {'legacy', 'horizontal_v1'}:
            raise ValueError('Invalid messaging dispatch mode')
        tenant = os.getenv('TEAM360_MESSAGING_DEV_SQL_TENANT', '').strip()
        if mode == 'horizontal_v1' and tenant:
            raise ValueError('Legacy SQL is incompatible with horizontal dispatch')
        if tenant and tenant != 'telchi':
            raise ValueError('Unsupported DEV SQL tenant')
        settings = cls(
            os.getenv("TEAM360_MESSAGING_WORKSPACE_SLUG", "").strip(),
            os.getenv("TEAM360_MESSAGING_CHANNEL_ALIAS", "").strip(),
            os.getenv("TEAM360_MESSAGING_DEV_AUTHORIZED_SENDER", "").strip(),
            os.getenv("TEAM360_MESSAGING_WEBHOOK_TOKEN", "").strip(),
            tenant or None,
            mode,
        )
        if (not settings.workspace_slug or not settings.channel_alias
                or (mode == 'legacy' and not re.fullmatch(r"[1-9][0-9]{6,14}", settings.authorized_sender))
                or len(settings.webhook_token) < 32):
            raise ValueError("Incomplete DEV messaging configuration")
        return settings

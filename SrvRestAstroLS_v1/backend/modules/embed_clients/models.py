from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EmbedClient:
    client_id: str
    hmac_secret: str
    assistant_instance_code: str
    organization_code: str
    workspace_code: str
    package_code: str
    knowledge_scope_code: str
    allowed_origins: list[str] = field(default_factory=list)
    is_active: bool = True

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> EmbedClient:
        allowed_origins_raw = row.get("allowed_origins") or []
        if isinstance(allowed_origins_raw, (list, tuple)):
            allowed_origins = list(allowed_origins_raw)
        else:
            allowed_origins = []
        return cls(
            client_id=str(row["client_id"]),
            hmac_secret=str(row["hmac_secret"]),
            assistant_instance_code=str(row["assistant_instance_code"]),
            organization_code=str(row["organization_code"]),
            workspace_code=str(row["workspace_code"]),
            package_code=str(row["package_code"]),
            knowledge_scope_code=str(row["knowledge_scope_code"]),
            allowed_origins=allowed_origins,
            is_active=bool(row.get("is_active", True)),
        )

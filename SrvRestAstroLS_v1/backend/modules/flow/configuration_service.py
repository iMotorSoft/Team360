"""Flow sector configuration domain service.

Reads and atomically updates the persistent routing policy that Flow already
consumes (``flow_sectors`` / ``flow_sector_levels``). Only existing levels can
be edited; creating or removing levels stays out of V1 scope. Destination is
trimmed before persisting; routings and closure approvals snapshot their
destinations at creation time, so updates affect future workflow events only.
"""

from __future__ import annotations

import re
from typing import Any

from psycopg_pool import AsyncConnectionPool

from modules.db.transaction import transaction

from .configuration_repository import FlowConfigurationPostgresRepository

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MAX_DESTINATION_LENGTH = 254

_ALLOWED_UPDATE_FIELDS = {"levels", "closure_approval_level"}

# Operational settings validation bounds.
_MIN_SCHEDULER_INTERVAL = 5
_MAX_SCHEDULER_INTERVAL = 3600
_MIN_BATCH_LIMIT = 1
_MAX_BATCH_LIMIT = 10000


def _validate_sla_seconds(value: Any) -> int | None:
    """Validate and normalize SLA seconds value.

    Returns None (no SLA) or a positive integer.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise FlowConfigurationValidationError("first_response_sla_seconds inválido")
    if isinstance(value, float):
        if value != int(value):
            raise FlowConfigurationValidationError(
                "first_response_sla_seconds debe ser un entero"
            )
        value = int(value)
    if not isinstance(value, int) or value <= 0:
        raise FlowConfigurationValidationError(
            "first_response_sla_seconds debe ser positivo o null"
        )
    return value


class FlowSectorNotFoundError(RuntimeError):
    pass


class FlowConfigurationValidationError(ValueError):
    pass


def _validate_destination(destination: str) -> str:
    if not isinstance(destination, str):
        raise FlowConfigurationValidationError("destination debe ser texto")
    value = destination.strip()
    if not value:
        raise FlowConfigurationValidationError("destination es obligatorio")
    if len(value) > _MAX_DESTINATION_LENGTH:
        raise FlowConfigurationValidationError("destination supera el largo máximo")
    if not _EMAIL_RE.match(value):
        raise FlowConfigurationValidationError("destination no es un email válido")
    return value


def _validate_closure_approval_level(
    closure_approval_level: Any, existing_levels: set[int]
) -> int | None:
    if closure_approval_level is None:
        return None
    if isinstance(closure_approval_level, bool):
        raise FlowConfigurationValidationError("closure_approval_level inválido")
    if not isinstance(closure_approval_level, int) or closure_approval_level <= 0:
        raise FlowConfigurationValidationError(
            "closure_approval_level debe ser un nivel positivo"
        )
    if closure_approval_level not in existing_levels:
        raise FlowConfigurationValidationError(
            "closure_approval_level no pertenece a los niveles del sector"
        )
    return closure_approval_level


def _validate_levels_payload(
    levels: Any, current_levels: list[dict]
) -> list[dict]:
    if not isinstance(levels, list):
        raise FlowConfigurationValidationError("levels debe ser una lista")

    existing = {item["level"]: item for item in current_levels}
    seen: set[int] = set()
    validated: list[dict] = []
    for entry in levels:
        if not isinstance(entry, dict):
            raise FlowConfigurationValidationError("cada nivel debe ser un objeto")
        unknown = set(entry) - {"level", "destination", "first_response_sla_seconds"}
        if unknown:
            raise FlowConfigurationValidationError(
                f"campos no permitidos en nivel: {sorted(unknown)}"
            )
        if "level" not in entry or "destination" not in entry:
            raise FlowConfigurationValidationError(
                "cada nivel debe incluir level y destination"
            )
        level = entry["level"]
        if isinstance(level, bool) or not isinstance(level, int) or level <= 0:
            raise FlowConfigurationValidationError("level inválido")
        if level in seen:
            raise FlowConfigurationValidationError("nivel duplicado en el payload")
        seen.add(level)
        if level not in existing:
            raise FlowConfigurationValidationError(
                f"el nivel {level} no existe en el sector"
            )
        destination = _validate_destination(entry["destination"])
        sla = entry.get("first_response_sla_seconds")
        validated.append({
            "level": level,
            "destination": destination,
            "first_response_sla_seconds": _validate_sla_seconds(sla),
        })
    return validated


class FlowConfigurationService:
    """Reads and atomically updates Flow routing configuration."""

    def __init__(
        self,
        *,
        pool: AsyncConnectionPool,
        repository: FlowConfigurationPostgresRepository | None = None,
    ) -> None:
        self._pool = pool
        self._repository = repository or FlowConfigurationPostgresRepository()

    @staticmethod
    def _canonical_sector(sector: dict, levels: list[dict]) -> dict[str, Any]:
        return {
            "sector_id": sector["sector_id"],
            "display_name": sector["display_name"],
            "active": sector["active"],
            "closure_approval_level": sector["closure_approval_level"],
            "levels": [
                {
                    "level": item["level"],
                    "channel": item["channel"],
                    "destination": item["destination"],
                    "active": item["active"],
                    "first_response_sla_seconds": item.get("first_response_sla_seconds"),
                }
                for item in levels
            ],
        }

    async def list_configurations(self) -> dict[str, Any]:
        async with transaction(self._pool) as conn:
            sectors = await self._repository.list_sectors(conn)
            levels = await self._repository.list_levels(conn)
        by_sector: dict[str, list[dict]] = {}
        for item in levels:
            by_sector.setdefault(item["sector_id"], []).append(item)
        return {
            "sectors": [
                self._canonical_sector(sector, by_sector.get(sector["sector_id"], []))
                for sector in sectors
            ]
        }

    async def get_configuration(self, sector_id: str) -> dict[str, Any] | None:
        async with transaction(self._pool) as conn:
            sector = await self._repository.get_sector(conn, sector_id)
            if sector is None:
                return None
            levels = await self._repository.get_levels(conn, sector_id)
        return self._canonical_sector(sector, levels)

    async def update_configuration(
        self,
        sector_id: str,
        *,
        levels: Any,
        closure_approval_level: Any,
    ) -> dict[str, Any] | None:
        """Validate and atomically apply a sector configuration update."""
        async with transaction(self._pool) as conn:
            sector = await self._repository.get_sector(conn, sector_id)
            if sector is None:
                raise FlowSectorNotFoundError(
                    f"Flow sector not found: {sector_id}"
                )
            current_levels = await self._repository.get_levels(conn, sector_id)

            validated_levels = _validate_levels_payload(levels, current_levels)
            existing_levels = {item["level"] for item in current_levels}
            validated_closure = _validate_closure_approval_level(
                closure_approval_level, existing_levels
            )

            for item in validated_levels:
                await self._repository.update_destination(
                    conn,
                    sector_id=sector_id,
                    level=item["level"],
                    destination=item["destination"],
                )
                await self._repository.update_first_response_sla(
                    conn,
                    sector_id=sector_id,
                    level=item["level"],
                    first_response_sla_seconds=item["first_response_sla_seconds"],
                )
            await self._repository.update_closure_approval_level(
                conn,
                sector_id=sector_id,
                closure_approval_level=validated_closure,
            )

            after = await self._repository.get_sector(conn, sector_id)
            after_levels = await self._repository.get_levels(conn, sector_id)
        assert after is not None
        return self._canonical_sector(after, after_levels)

    # --- Operational settings ---

    async def get_operational_settings(self) -> dict[str, Any]:
        async with transaction(self._pool) as conn:
            return await self._repository.get_operational_settings(conn)

    async def update_operational_settings(
        self,
        *,
        automation_enabled: bool | None = None,
        scheduler_interval_seconds: int | None = None,
        mail_intake_enabled: bool | None = None,
        mail_batch_limit: int | None = None,
        mail_after_cutoff: bool | None = None,
    ) -> dict[str, Any]:
        """Validate and persist Flow operational settings."""
        if scheduler_interval_seconds is not None:
            if (
                not isinstance(scheduler_interval_seconds, int)
                or scheduler_interval_seconds < _MIN_SCHEDULER_INTERVAL
                or scheduler_interval_seconds > _MAX_SCHEDULER_INTERVAL
            ):
                raise FlowConfigurationValidationError(
                    f"scheduler_interval_seconds debe estar entre {_MIN_SCHEDULER_INTERVAL} y {_MAX_SCHEDULER_INTERVAL}"
                )
        if mail_batch_limit is not None:
            if (
                not isinstance(mail_batch_limit, int)
                or mail_batch_limit < _MIN_BATCH_LIMIT
                or mail_batch_limit > _MAX_BATCH_LIMIT
            ):
                raise FlowConfigurationValidationError(
                    f"mail_batch_limit debe estar entre {_MIN_BATCH_LIMIT} y {_MAX_BATCH_LIMIT}"
                )
        async with transaction(self._pool) as conn:
            return await self._repository.update_operational_settings(
                conn,
                automation_enabled=automation_enabled,
                scheduler_interval_seconds=scheduler_interval_seconds,
                mail_intake_enabled=mail_intake_enabled,
                mail_batch_limit=mail_batch_limit,
                mail_after_cutoff=mail_after_cutoff,
            )

import asyncio
from copy import deepcopy

import pytest

from modules.flow.configuration_service import (
    FlowConfigurationService,
    FlowConfigurationValidationError,
    FlowSectorNotFoundError,
)

_SECTOR = {
    "sector_id": "alumbrado",
    "display_name": "Alumbrado Público",
    "active": True,
    "closure_approval_level": 2,
}

_LEVELS = [
    {
        "id": "l1",
        "sector_id": "alumbrado",
        "level": 1,
        "channel": "email",
        "destination": "alumbrado.n1@alquimiablue.com",
        "active": True,
        "first_response_sla_seconds": 30,
    },
    {
        "id": "l2",
        "sector_id": "alumbrado",
        "level": 2,
        "channel": "email",
        "destination": "alumbrado.n2@alquimiablue.com",
        "active": True,
        "first_response_sla_seconds": 30,
    },
    {
        "id": "l3",
        "sector_id": "alumbrado",
        "level": 3,
        "channel": "email",
        "destination": "alumbrado.n3@alquimiablue.com",
        "active": True,
        "first_response_sla_seconds": None,
    },
]


class _FakeRepository:
    def __init__(self, sector=None, levels=None, fail_update: bool = False):
        self.sector = deepcopy(sector) if sector is not None else deepcopy(_SECTOR)
        self.levels = deepcopy(levels) if levels is not None else deepcopy(_LEVELS)
        self.fail_update = fail_update
        self.destination_writes = []
        self.closure_writes = []

    async def list_sectors(self, conn):
        return [self.sector]

    async def list_levels(self, conn):
        return self.levels

    async def get_sector(self, conn, sector_id):
        if self.sector and self.sector["sector_id"] == sector_id:
            return deepcopy(self.sector)
        return None

    async def get_levels(self, conn, sector_id):
        if self.sector and self.sector["sector_id"] == sector_id:
            return deepcopy(self.levels)
        return []

    async def update_destination(self, conn, *, sector_id, level, destination):
        if self.fail_update:
            raise RuntimeError("boom")
        self.destination_writes.append((level, destination))
        for item in self.levels:
            if item["level"] == level:
                item["destination"] = destination
        return 1

    async def update_first_response_sla(self, conn, *, sector_id, level, first_response_sla_seconds):
        if self.fail_update:
            raise RuntimeError("boom")
        for item in self.levels:
            if item["level"] == level:
                item["first_response_sla_seconds"] = first_response_sla_seconds
        return 1

    async def get_operational_settings(self, conn):
        return {
            "automation_enabled": False,
            "scheduler_interval_seconds": 15,
            "mail_intake_enabled": True,
            "mail_batch_limit": 500,
            "mail_after_cutoff": True,
            "mail_cutoff_epoch": 1787239323,
        }

    async def update_operational_settings(self, conn, **kwargs):
        return {
            "automation_enabled": False,
            "scheduler_interval_seconds": 15,
            "mail_intake_enabled": True,
            "mail_batch_limit": 500,
            "mail_after_cutoff": True,
            "mail_cutoff_epoch": kwargs.get("mail_cutoff_epoch", 1787239323),
        }

    async def update_closure_approval_level(self, conn, *, sector_id, closure_approval_level):
        self.closure_writes.append(closure_approval_level)
        self.sector["closure_approval_level"] = closure_approval_level
        return 1


class _FakePool:
    def __init__(self, repository):
        self._repository = repository

    def connection(self):
        return _Connection(self._repository)


class _Connection:
    def __init__(self, repository):
        self._repository = repository

    def transaction(self):
        return _Transaction(self._repository)


class _Transaction:
    def __init__(self, repository):
        self._repository = repository

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _service(monkeypatch, repository=None) -> FlowConfigurationService:
    repo = repository or _FakeRepository()
    service = FlowConfigurationService(pool=_FakePool(repo), repository=repo)
    monkeypatch.setattr(
        "modules.flow.configuration_service.transaction",
        lambda pool: pool.connection().transaction(),
    )
    return service


def test_read_returns_canonical_shape(monkeypatch):
    service = _service(monkeypatch)
    result = asyncio.run(service.list_configurations())
    assert "sectors" in result
    sector = result["sectors"][0]
    assert sector["sector_id"] == "alumbrado"
    assert sector["closure_approval_level"] == 2
    assert [item["level"] for item in sector["levels"]] == [1, 2, 3]


def test_update_valid_persists_and_returns_canonical(monkeypatch):
    repo = _FakeRepository()
    service = _service(monkeypatch, repo)
    result = asyncio.run(
        service.update_configuration(
            "alumbrado",
            levels=[
                {"level": 1, "destination": "nuevo.n1@alquimiablue.com"},
                {"level": 2, "destination": "alumbrado.n2@alquimiablue.com"},
                {"level": 3, "destination": "alumbrado.n3@alquimiablue.com"},
            ],
            closure_approval_level=2,
        )
    )
    assert result["sector_id"] == "alumbrado"
    assert repo.destination_writes[0] == (1, "nuevo.n1@alquimiablue.com")
    assert repo.closure_writes == [2]
    by_level = {item["level"]: item["destination"] for item in result["levels"]}
    assert by_level[1] == "nuevo.n1@alquimiablue.com"


def test_update_trims_destination(monkeypatch):
    repo = _FakeRepository()
    service = _service(monkeypatch, repo)
    result = asyncio.run(
        service.update_configuration(
            "alumbrado",
            levels=[
                {"level": 1, "destination": "  nuevo.n1@alquimiablue.com  "},
                {"level": 2, "destination": "alumbrado.n2@alquimiablue.com"},
                {"level": 3, "destination": "alumbrado.n3@alquimiablue.com"},
            ],
            closure_approval_level=2,
        )
    )
    by_level = {item["level"]: item["destination"] for item in result["levels"]}
    assert by_level[1] == "nuevo.n1@alquimiablue.com"
    assert repo.destination_writes[0] == (1, "nuevo.n1@alquimiablue.com")


@pytest.mark.parametrize(
    "destination",
    ["", "   ", "alumbrado.n1", "@alquimiablue.com", "a b@dominio.com"],
)
def test_update_invalid_destination_rejected(monkeypatch, destination):
    repo = _FakeRepository()
    service = _service(monkeypatch, repo)
    with pytest.raises(FlowConfigurationValidationError):
        asyncio.run(
            service.update_configuration(
                "alumbrado",
                levels=[
                    {"level": 1, "destination": destination},
                    {"level": 2, "destination": "alumbrado.n2@alquimiablue.com"},
                    {"level": 3, "destination": "alumbrado.n3@alquimiablue.com"},
                ],
                closure_approval_level=2,
            )
        )
    assert repo.destination_writes == []


def test_update_unknown_level_rejected(monkeypatch):
    service = _service(monkeypatch)
    with pytest.raises(FlowConfigurationValidationError):
        asyncio.run(
            service.update_configuration(
                "alumbrado",
                levels=[{"level": 99, "destination": "x@y.com"}],
                closure_approval_level=2,
            )
        )


def test_update_duplicate_level_rejected(monkeypatch):
    service = _service(monkeypatch)
    with pytest.raises(FlowConfigurationValidationError):
        asyncio.run(
            service.update_configuration(
                "alumbrado",
                levels=[
                    {"level": 1, "destination": "a@b.com"},
                    {"level": 1, "destination": "c@d.com"},
                ],
                closure_approval_level=2,
            )
        )


def test_update_unknown_field_in_level_rejected(monkeypatch):
    service = _service(monkeypatch)
    with pytest.raises(FlowConfigurationValidationError):
        asyncio.run(
            service.update_configuration(
                "alumbrado",
                levels=[{"level": 1, "destination": "a@b.com", "role": "hack"}],
                closure_approval_level=2,
            )
        )


@pytest.mark.parametrize(
    "closure",
    [99, 0, -1, True],
)
def test_update_invalid_closure_level_rejected(monkeypatch, closure):
    repo = _FakeRepository()
    service = _service(monkeypatch, repo)
    with pytest.raises(FlowConfigurationValidationError):
        asyncio.run(
            service.update_configuration(
                "alumbrado",
                levels=[
                    {"level": 1, "destination": "a@b.com"},
                    {"level": 2, "destination": "c@d.com"},
                    {"level": 3, "destination": "e@f.com"},
                ],
                closure_approval_level=closure,
            )
        )
    assert repo.destination_writes == []


def test_update_null_closure_level_allowed(monkeypatch):
    repo = _FakeRepository()
    service = _service(monkeypatch, repo)
    result = asyncio.run(
        service.update_configuration(
            "alumbrado",
            levels=[
                {"level": 1, "destination": "a@b.com"},
                {"level": 2, "destination": "c@d.com"},
                {"level": 3, "destination": "e@f.com"},
            ],
            closure_approval_level=None,
        )
    )
    assert result["closure_approval_level"] is None
    assert repo.closure_writes == [None]


def test_update_single_level_sector_does_not_require_upper_levels(monkeypatch):
    sector = {
        "sector_id": "baches",
        "display_name": "Baches",
        "active": True,
        "closure_approval_level": None,
    }
    levels = [
        {
            "id": "baches-l1",
            "sector_id": "baches",
            "level": 1,
            "channel": "email",
            "destination": "baches.n1@alquimiablue.com",
            "active": True,
            "first_response_sla_seconds": 30,
        }
    ]
    repo = _FakeRepository(sector=sector, levels=levels)
    service = _service(monkeypatch, repo)
    result = asyncio.run(
        service.update_configuration(
            "baches",
            levels=[
                {
                    "level": 1,
                    "destination": "baches.n1@alquimiablue.com",
                    "first_response_sla_seconds": 30,
                }
            ],
            closure_approval_level=None,
        )
    )
    assert [item["level"] for item in result["levels"]] == [1]
    assert result["closure_approval_level"] is None


def test_update_unknown_sector_raises_not_found(monkeypatch):
    repo = _FakeRepository(sector=None, levels=[])
    service = _service(monkeypatch, repo)
    with pytest.raises(FlowSectorNotFoundError):
        asyncio.run(
            service.update_configuration(
                "inexistente",
                levels=[{"level": 1, "destination": "a@b.com"}],
                closure_approval_level=None,
            )
        )


def test_update_failure_rolls_back_no_partial_writes(monkeypatch):
    # The service relies on the caller-owned transaction for rollback; if the
    # repository raises mid-update the exception must propagate and no
    # partial destination may be reported as persisted.
    repo = _FakeRepository(fail_update=True)
    service = _service(monkeypatch, repo)
    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(
            service.update_configuration(
                "alumbrado",
                levels=[
                    {"level": 1, "destination": "a@b.com"},
                    {"level": 2, "destination": "c@d.com"},
                    {"level": 3, "destination": "e@f.com"},
                ],
                closure_approval_level=2,
            )
        )
    assert repo.destination_writes == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("automation_enabled", "true"),
        ("mail_intake_enabled", 1),
        ("mail_after_cutoff", None),
        ("scheduler_interval_seconds", True),
        ("mail_batch_limit", False),
    ],
)
def test_invalid_operational_types_rejected(monkeypatch, field, value):
    if field == "mail_after_cutoff" and value is None:
        value = "false"
    service = _service(monkeypatch)
    with pytest.raises(FlowConfigurationValidationError):
        asyncio.run(service.update_operational_settings(**{field: value}))


@pytest.mark.parametrize(
    "cutoff",
    [True, 0, -1, 1577836799, 1893456001, 1.5, "1787239323"],
)
def test_invalid_mail_cutoff_epoch_rejected(monkeypatch, cutoff):
    service = _service(monkeypatch)
    with pytest.raises(FlowConfigurationValidationError):
        asyncio.run(
            service.update_operational_settings(mail_cutoff_epoch=cutoff)
        )


def test_valid_mail_cutoff_epoch_is_persisted(monkeypatch):
    service = _service(monkeypatch)
    result = asyncio.run(
        service.update_operational_settings(mail_cutoff_epoch=1787239368)
    )
    assert result["mail_cutoff_epoch"] == 1787239368

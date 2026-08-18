import asyncio

import pytest

from modules.flow.executive_list_service import (
    FlowExecutiveListService,
    FlowExecutiveListValidationError,
)


class _Transaction:
    async def __aenter__(self):
        return _Connection()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Pool:
    def connection(self):
        return _Transaction()


class _Connection:
    def transaction(self):
        return _Transaction()


class _Repository:
    def __init__(self, rows=None, sectors=None):
        self.rows = rows or []
        self.sectors = sectors or []
        self.arguments = None

    async def list_cases(self, conn, **kwargs):
        self.arguments = kwargs
        return self.rows

    async def list_sector_options(self, conn):
        return self.sectors


def test_list_service_normalizes_filters_and_metadata():
    repository = _Repository(
        rows=[
            {
                "request_id": "r-1",
                "status": "ACTIVE",
                "total_count": 21,
            }
        ],
        sectors=[{"sector_id": "alumbrado", "display_name": "Alumbrado"}],
    )

    result = asyncio.run(
        FlowExecutiveListService(pool=_Pool(), repository=repository).list_cases(
            page=2,
            page_size=10,
            status="open",
            sector_id=" alumbrado ",
            search="luminaria_%",
            sla_status="BREACHED",
            escalated=True,
        )
    )

    assert result["items"] == [{"request_id": "r-1", "status": "ACTIVE"}]
    assert result["sectors"] == [{"sector_id": "alumbrado", "display_name": "Alumbrado"}]
    assert result["pagination"] == {
        "page": 2,
        "page_size": 10,
        "total": 21,
        "has_next": True,
    }
    assert repository.arguments["statuses"] == ("ACTIVE", "CONFIRMED")
    assert repository.arguments["sector_id"] == "alumbrado"
    assert repository.arguments["search"] == "luminaria_%"
    assert repository.arguments["sla_status"] == "BREACHED"
    assert repository.arguments["escalated"] is True
    assert repository.arguments["offset"] == 10


@pytest.mark.parametrize(
    "kwargs",
    [
        {"page": 0},
        {"page_size": 0},
        {"page_size": 101},
        {"status": "not-a-status"},
        {"sla_status": "LATE"},
        {"search": "x" * 201},
    ],
)
def test_list_service_rejects_invalid_pagination_and_filters(kwargs):
    with pytest.raises(FlowExecutiveListValidationError):
        asyncio.run(FlowExecutiveListService(pool=_Pool(), repository=_Repository()).list_cases(**kwargs))

"""Read-only executive case view building for Directorio queries.

The executive view is derived exclusively from persisted Flow facts: for
RESOLVED cases it prefers the immutable ``flow_case_audit_records`` snapshot
(``AUDIT_SNAPSHOT``), for open cases it builds a live view from the operational
tables (``LIVE``). No workflow mutation happens here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

LIVE = "LIVE"
AUDIT_SNAPSHOT = "AUDIT_SNAPSHOT"

# Deterministic operational truth exposed to the LLM so it can never
# contradict the persisted state.
FACT_CLOSED = "closed"
FACT_OPEN = "open"
FACT_PENDING_APPROVAL = "pending_approval"


def executive_closure_fact(status: str) -> str:
    """Map the request lifecycle to the single closure fact the LLM may use."""
    if status == "RESOLVED":
        return FACT_CLOSED
    if status == "RESOLUTION_PENDING_APPROVAL":
        return FACT_PENDING_APPROVAL
    return FACT_OPEN


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _elapsed(start: datetime, end: datetime) -> int:
    return max(0, int((end - start).total_seconds()))


def _first_response_at(routing_history: list[dict[str, Any]]) -> datetime | None:
    candidates = [
        _parse_dt(routing.get("first_response_at"))
        for routing in routing_history
        if routing.get("first_response_at")
    ]
    return min(candidates) if candidates else None


def build_executive_view(
    snapshot: dict[str, Any],
    *,
    data_source: str,
    request_status: str,
    audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize a snapshot into the Directorio-oriented view contract."""
    request = snapshot.get("request") or {}
    return {
        "request_id": request.get("request_id"),
        "status": request_status,
        "data_source": data_source,
        "request": request,
        "routing_history": snapshot.get("routings") or [],
        "sla": snapshot.get("slas") or [],
        "escalations": snapshot.get("escalations") or [],
        "operational_events": snapshot.get("operations") or [],
        "resolution": snapshot.get("resolution"),
        "closure_approval": snapshot.get("approval"),
        "result": snapshot.get("result") or {},
        "metrics": dict(snapshot.get("metrics") or {}),
        "timeline": snapshot.get("timeline") or [],
        "audit": audit,
        "status_fact": executive_closure_fact(request_status),
        "executive_summary": None,
    }


def augment_metrics(view: dict[str, Any], *, now: datetime | None = None) -> None:
    """Add derived metrics without inventing facts.

    ``first_response_elapsed_seconds`` is the time from intake to the first
    operational first response; ``current_age_seconds`` only for open cases.
    """
    request = view.get("request") or {}
    metrics = view["metrics"]
    received_at = _parse_dt(request.get("received_at"))
    first_response = _first_response_at(view.get("routing_history") or [])
    if received_at is not None and first_response is not None:
        metrics["first_response_elapsed_seconds"] = _elapsed(received_at, first_response)
    if view.get("status_fact") != FACT_CLOSED and received_at is not None:
        metrics["current_age_seconds"] = _elapsed(
            received_at, now or datetime.now(timezone.utc)
        )


def executive_context(view: dict[str, Any]) -> dict[str, Any]:
    """Compact, traceable facts handed to the LLM interpreter."""
    return {
        "status_fact": view.get("status_fact"),
        "data_source": view.get("data_source"),
        "request": {
            key: view["request"].get(key)
            for key in (
                "request_id",
                "sector_name",
                "category",
                "description",
                "location",
                "received_at",
                "confirmed_at",
            )
        },
        "routing_history": [
            {
                "routing_id": row.get("routing_id"),
                "routing_key": row.get("routing_key"),
                "level": row.get("level"),
                "destination": row.get("destination"),
                "assigned_at": row.get("assigned_at"),
                "work_status": row.get("work_status"),
                "first_response_at": row.get("first_response_at"),
                "first_responder": row.get("first_responder"),
            }
            for row in view.get("routing_history") or []
        ],
        "sla": [
            {
                "sla_id": row.get("sla_id"),
                "level": row.get("level"),
                "duration_seconds": row.get("duration_seconds"),
                "started_at": row.get("started_at"),
                "due_at": row.get("due_at"),
                "status": row.get("status"),
                "first_response_at": row.get("first_response_at"),
            }
            for row in view.get("sla") or []
        ],
        "escalations": [
            {
                "escalation_id": row.get("escalation_id"),
                "from_level": row.get("from_level"),
                "to_level": row.get("to_level"),
                "trigger": row.get("trigger"),
                "created_at": row.get("created_at"),
                "status": row.get("status"),
            }
            for row in view.get("escalations") or []
        ],
        "operational_events": [
            {
                "event_id": row.get("event_id"),
                "level": row.get("level"),
                "received_at": row.get("received_at"),
                "interpretation": row.get("interpretation"),
            }
            for row in view.get("operational_events") or []
        ],
        "resolution": view.get("resolution"),
        "closure_approval": view.get("closure_approval"),
        "result": view.get("result"),
        "metrics": view.get("metrics"),
        "timeline": view.get("timeline") or [],
        "audit": view.get("audit"),
    }

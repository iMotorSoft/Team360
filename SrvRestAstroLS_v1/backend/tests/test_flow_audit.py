from datetime import datetime, timezone

from modules.flow.audit_repository import (
    build_timeline,
    canonical_json,
    compute_metrics,
    sha256_of_snapshot,
)


def _dt(iso):
    return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)


def test_canonical_json_ignores_key_insertion_order():
    a = {"b": 1, "a": {"d": 2, "c": 3}}
    b = {"a": {"c": 3, "d": 2}, "b": 1}
    assert canonical_json(a) == canonical_json(b)


def test_sha256_is_stable_and_detects_change():
    snapshot = {"result": {"status": "RESOLVED"}, "metrics": {"count": 1}}
    assert sha256_of_snapshot(snapshot) == sha256_of_snapshot(dict(snapshot))
    changed = {"result": {"status": "RESOLVED"}, "metrics": {"count": 2}}
    assert sha256_of_snapshot(changed) != sha256_of_snapshot(snapshot)
    assert len(sha256_of_snapshot(snapshot)) == 64


def test_compute_metrics_counts_slas_and_elapsed():
    received = _dt("2026-08-13T00:00:00Z")
    resolved = _dt("2026-08-13T01:00:00Z")
    slas = [
        {"status": "MET"},
        {"status": "BREACHED"},
        {"status": "BREACHED"},
    ]
    metrics = compute_metrics(
        received_at=received,
        resolved_at=resolved,
        routing_count=3,
        escalation_count=2,
        slas=slas,
        levels_reached=3,
    )
    assert metrics["total_elapsed_seconds"] == 3600
    assert metrics["routing_count"] == 3
    assert metrics["escalation_count"] == 2
    assert metrics["sla_total"] == 3
    assert metrics["sla_met_count"] == 1
    assert metrics["sla_breached_count"] == 2
    assert metrics["levels_reached"] == 3


def test_build_timeline_is_chronological_and_complete():
    received = _dt("2026-08-13T00:00:00Z")
    confirmed = _dt("2026-08-13T00:01:00Z")
    assigned = _dt("2026-08-13T00:02:00Z")
    breached = _dt("2026-08-13T00:05:00Z")
    proposed = _dt("2026-08-13T00:10:00Z")
    decided = _dt("2026-08-13T00:12:00Z")

    routings = [{"routing_id": "r1", "routing_key": "initial_n1", "level": 1, "assigned_at": assigned.isoformat()}]
    slas = [
        {
            "sla_id": "s1", "routing_id": "r1", "level": 1,
            "started_at": assigned.isoformat(), "status": "BREACHED",
            "met_at": None, "breached_at": breached.isoformat(),
        }
    ]
    escalations = [{"escalation_id": "e1", "to_routing_id": "r2", "to_level": 2, "created_at": breached.isoformat()}]
    resolution = {"resolution_id": "res1", "proposed_at": proposed.isoformat(), "routing_id": "r3"}
    approval = {"approval_id": "a1", "decision_at": decided.isoformat(), "decision": "APPROVED"}

    timeline = build_timeline(
        received_at=received,
        confirmed_at=confirmed,
        routings=routings,
        slas=slas,
        escalations=escalations,
        resolution=resolution,
        approval=approval,
    )

    types = [item["event_type"] for item in timeline]
    assert types == [
        "REQUEST_RECEIVED",
        "REQUEST_CONFIRMED",
        "ROUTING_ASSIGNED",
        "SLA_STARTED",
        "SLA_BREACHED",
        "ESCALATED",
        "RESOLUTION_PROPOSED",
        "CLOSURE_APPROVED",
        "REQUEST_RESOLVED",
    ]
    stamps = [item["timestamp"] for item in timeline]
    assert stamps == sorted(stamps)
    assert timeline[-1]["event_type"] == "REQUEST_RESOLVED"


def test_build_timeline_rejected_approval_has_no_closure_events():
    """Un cierre REJECTED no genera CLOSURE_APPROVED ni REQUEST_RESOLVED."""
    received = _dt("2026-08-13T00:00:00Z")
    confirmed = _dt("2026-08-13T00:01:00Z")
    proposed = _dt("2026-08-13T00:10:00Z")
    decided = _dt("2026-08-13T00:12:00Z")

    timeline = build_timeline(
        received_at=received,
        confirmed_at=confirmed,
        routings=[],
        slas=[],
        escalations=[],
        resolution={
            "resolution_id": "res1",
            "proposed_at": proposed.isoformat(),
            "routing_id": "r3",
        },
        approval={
            "approval_id": "a1",
            "decision_at": decided.isoformat(),
            "status": "REJECTED",
        },
    )

    types = [item["event_type"] for item in timeline]
    assert types == ["REQUEST_RECEIVED", "REQUEST_CONFIRMED", "RESOLUTION_PROPOSED"]
    assert "CLOSURE_APPROVED" not in types
    assert "REQUEST_RESOLVED" not in types


def test_build_timeline_pending_approval_has_no_closure_events():
    """Un cierre PENDING (sin decisión) no emite eventos de cierre."""
    received = _dt("2026-08-13T00:00:00Z")
    confirmed = _dt("2026-08-13T00:01:00Z")
    proposed = _dt("2026-08-13T00:10:00Z")

    timeline = build_timeline(
        received_at=received,
        confirmed_at=confirmed,
        routings=[],
        slas=[],
        escalations=[],
        resolution={
            "resolution_id": "res1",
            "proposed_at": proposed.isoformat(),
            "routing_id": "r3",
        },
        approval={"approval_id": "a1", "decision_at": None, "status": "PENDING"},
    )

    types = [item["event_type"] for item in timeline]
    assert types == ["REQUEST_RECEIVED", "REQUEST_CONFIRMED", "RESOLUTION_PROPOSED"]
    assert "CLOSURE_APPROVED" not in types
    assert "REQUEST_RESOLVED" not in types


def test_build_timeline_records_approval_resend_without_closing_case():
    timeline = build_timeline(
        received_at=_dt("2026-08-13T00:00:00Z"),
        confirmed_at=_dt("2026-08-13T00:01:00Z"),
        routings=[],
        slas=[],
        escalations=[],
        resolution={
            "resolution_id": "res1",
            "proposed_at": "2026-08-13T00:10:00+00:00",
            "routing_id": "r1",
        },
        approval={"approval_id": "a1", "decision_at": None, "status": "PENDING"},
        approval_resends=[
            {
                "approval_id": "a1",
                "approver_level": 2,
                "recipient": "alumbrado.n2@alquimiablue.com",
                "occurred_at": "2026-08-13T00:11:00+00:00",
            }
        ],
    )

    resend = next(item for item in timeline if item["event_type"] == "APPROVAL_NOTIFICATION_RESENT")
    assert resend["level"] == 2
    assert resend["recipient"] == "alumbrado.n2@alquimiablue.com"
    assert "REQUEST_RESOLVED" not in [item["event_type"] for item in timeline]

"""Immutable, hash-verified case audit snapshot for Directorio/Auditoria."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from psycopg import AsyncConnection

from modules.db.transaction import execute, fetch_all, fetch_one

from .domain import AUDIT_SCHEMA_VERSION


def canonical_json(snapshot: dict[str, Any]) -> str:
    """Deterministic JSON serialization independent of key insertion order."""
    return json.dumps(
        snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def sha256_of_snapshot(snapshot: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(snapshot).encode("utf-8")).hexdigest()


def _iso(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return value.isoformat()


def compute_metrics(
    *,
    received_at: datetime | None,
    resolved_at: datetime | None,
    routing_count: int,
    escalation_count: int,
    slas: list[dict[str, Any]],
    levels_reached: int,
) -> dict[str, Any]:
    sla_met = sum(1 for sla in slas if sla.get("status") == "MET")
    sla_breached = sum(1 for sla in slas if sla.get("status") == "BREACHED")
    elapsed = None
    if received_at is not None and resolved_at is not None:
        elapsed = int((resolved_at - received_at).total_seconds())
    return {
        "total_elapsed_seconds": elapsed,
        "routing_count": routing_count,
        "escalation_count": escalation_count,
        "sla_total": len(slas),
        "sla_met_count": sla_met,
        "sla_breached_count": sla_breached,
        "levels_reached": levels_reached,
    }


def _event(timestamp, event_type, *, routing_id=None, level=None, reference_id=None):
    return {
        "timestamp": _iso(timestamp),
        "event_type": event_type,
        "routing_id": routing_id,
        "level": level,
        "reference_id": reference_id,
    }


def build_timeline(
    *,
    received_at,
    confirmed_at,
    routings: list[dict[str, Any]],
    slas: list[dict[str, Any]],
    escalations: list[dict[str, Any]],
    resolution: dict[str, Any] | None,
    approval: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    items.append(_event(received_at, "REQUEST_RECEIVED"))
    items.append(_event(confirmed_at, "REQUEST_CONFIRMED"))
    for routing in routings:
        items.append(
            _event(
                routing.get("assigned_at"),
                "ROUTING_ASSIGNED",
                routing_id=routing.get("routing_id"),
                level=routing.get("level"),
                reference_id=routing.get("routing_key"),
            )
        )
    for sla in slas:
        items.append(
            _event(
                sla.get("started_at"),
                "SLA_STARTED",
                routing_id=sla.get("routing_id"),
                level=sla.get("level"),
                reference_id=sla.get("sla_id"),
            )
        )
        if sla.get("status") == "MET":
            items.append(
                _event(
                    sla.get("met_at"),
                    "SLA_MET",
                    routing_id=sla.get("routing_id"),
                    level=sla.get("level"),
                    reference_id=sla.get("sla_id"),
                )
            )
        elif sla.get("status") == "BREACHED":
            items.append(
                _event(
                    sla.get("breached_at"),
                    "SLA_BREACHED",
                    routing_id=sla.get("routing_id"),
                    level=sla.get("level"),
                    reference_id=sla.get("sla_id"),
                )
            )
    for escalation in escalations:
        items.append(
            _event(
                escalation.get("created_at"),
                "ESCALATED",
                routing_id=escalation.get("to_routing_id"),
                level=escalation.get("to_level"),
                reference_id=escalation.get("escalation_id"),
            )
        )
    if resolution is not None:
        items.append(
            _event(
                resolution.get("proposed_at"),
                "RESOLUTION_PROPOSED",
                routing_id=resolution.get("routing_id"),
                reference_id=resolution.get("resolution_id"),
            )
        )
    if approval is not None:
        items.append(
            _event(
                approval.get("decision_at"),
                "CLOSURE_APPROVED",
                reference_id=approval.get("approval_id"),
            )
        )
        items.append(
            _event(
                approval.get("decision_at"),
                "REQUEST_RESOLVED",
                reference_id=approval.get("approval_id"),
            )
        )
    items = [item for item in items if item["timestamp"] is not None]
    items.sort(key=lambda item: item["timestamp"])
    return items


class FlowAuditRepository:
    async def build_snapshot(
        self, conn: AsyncConnection, request_id: str
    ) -> dict[str, Any]:
        request = await fetch_one(
            conn,
            """
            select fr.id::text as request_id, fr.conversation_id::text,
                   fr.description, fr.tentative_category as category,
                   fr.location_text, fr.confirmed_at_utc, fr.status,
                   fc.citizen_address, fc.channel as origin_channel
            from flow_requests fr
            join flow_conversations fc on fc.id = fr.conversation_id
            where fr.id = %(request_id)s
            """,
            {"request_id": request_id},
        )
        if request is None:
            raise RuntimeError("Flow audit snapshot request not found.")

        received = await fetch_one(
            conn,
            """
            select min(occurred_at_utc) as received_at
            from flow_messages
            where conversation_id = %(conversation_id)s
              and direction = 'inbound'
            """,
            {"conversation_id": request["conversation_id"]},
        )
        sector = await fetch_one(
            conn,
            """
            select fsec.sector_id, fsec.display_name
            from flow_request_routings frr
            join flow_sectors fsec on fsec.sector_id = frr.sector_id
            where frr.request_id = %(request_id)s
            order by frr.level
            limit 1
            """,
            {"request_id": request_id},
        )

        routings = await fetch_all(
            conn,
            """
            select frr.id::text as routing_id, frr.routing_key,
                   frr.level::int, frr.destination, frr.assigned_at_utc,
                   frr.status as routing_status,
                   fws.operational_status as work_status,
                   fws.first_response_at_utc, fws.first_responder
            from flow_request_routings frr
            left join flow_request_work_states fws on fws.routing_id = frr.id
            where frr.request_id = %(request_id)s
            order by frr.level, frr.assigned_at_utc
            """,
            {"request_id": request_id},
        )

        slas = await fetch_all(
            conn,
            """
            select fs.id::text as sla_id, fs.routing_id::text,
                   frr.level::int, fs.sla_type, fs.duration_seconds,
                   fs.started_at_utc, fs.due_at_utc, fs.status,
                   fs.met_at_utc, fs.breached_at_utc,
                   fws.first_response_at_utc
            from flow_request_slas fs
            join flow_request_routings frr on frr.id = fs.routing_id
            left join flow_request_work_states fws on fws.routing_id = fs.routing_id
            where fs.request_id = %(request_id)s
            order by frr.level
            """,
            {"request_id": request_id},
        )

        escalations = await fetch_all(
            conn,
            """
            select fe.id::text as escalation_id, fe.from_routing_id::text,
                   fe.from_level::int, fe.to_routing_id::text,
                   fe.to_level::int, fe.trigger_type,
                   fe.trigger_sla_id::text, fe.created_at_utc,
                   fe.completed_at_utc, fe.status
            from flow_request_escalations fe
            where fe.request_id = %(request_id)s
            order by fe.created_at_utc
            """,
            {"request_id": request_id},
        )

        operations = await fetch_all(
            conn,
            """
            select foe.id::text as event_id, foe.routing_id::text,
                   frr.level::int, foe.response_received_at_utc,
                   foe.interpretation_action, foe.responder_address
            from flow_request_operational_events foe
            join flow_request_routings frr on frr.id = foe.routing_id
            where foe.request_id = %(request_id)s
            order by foe.response_received_at_utc
            """,
            {"request_id": request_id},
        )

        approval = await fetch_one(
            conn,
            """
            select id::text as approval_id, request_id::text,
                   resolution_id::text, approver_level::int,
                   approver_destination, status, outbound_external_message_id,
                   decision_source_external_message_id, decided_by,
                   decided_at_utc, decision_reason
            from flow_closure_approvals
            where request_id = %(request_id)s
            order by created_at_utc desc
            limit 1
            """,
            {"request_id": request_id},
        )

        resolution = None
        if approval is not None:
            resolution = await fetch_one(
                conn,
                """
                select id::text as resolution_id, request_id::text,
                       routing_id::text, status, proposed_by,
                       proposed_at_utc, resolution_text
                from flow_request_resolutions
                where id = %(resolution_id)s
                """,
                {"resolution_id": approval["resolution_id"]},
            )

        received_at = received["received_at"] if received else None
        resolved_at = approval["decided_at_utc"] if approval else None

        routing_list = [
            {
                "routing_id": row["routing_id"],
                "routing_key": row["routing_key"],
                "level": row["level"],
                "destination": row["destination"],
                "assigned_at": _iso(row["assigned_at_utc"]),
                "routing_status": row["routing_status"],
                "work_status": row["work_status"],
                "first_response_at": _iso(row["first_response_at_utc"]),
                "first_responder": row["first_responder"],
            }
            for row in routings
        ]
        sla_list = [
            {
                "sla_id": row["sla_id"],
                "sla_type": row["sla_type"],
                "routing_id": row["routing_id"],
                "level": row["level"],
                "duration_seconds": row["duration_seconds"],
                "started_at": _iso(row["started_at_utc"]),
                "due_at": _iso(row["due_at_utc"]),
                "first_response_at": _iso(row["first_response_at_utc"]),
                "status": row["status"],
                "met_at": _iso(row["met_at_utc"]),
                "breached_at": _iso(row["breached_at_utc"]),
            }
            for row in slas
        ]
        escalation_list = [
            {
                "escalation_id": row["escalation_id"],
                "from_routing_id": row["from_routing_id"],
                "from_level": row["from_level"],
                "to_routing_id": row["to_routing_id"],
                "to_level": row["to_level"],
                "trigger": row["trigger_type"],
                "trigger_sla_id": row["trigger_sla_id"],
                "created_at": _iso(row["created_at_utc"]),
                "completed_at": _iso(row["completed_at_utc"]),
                "status": row["status"],
            }
            for row in escalations
        ]
        operation_list = [
            {
                "event_id": row["event_id"],
                "routing_id": row["routing_id"],
                "level": row["level"],
                "received_at": _iso(row["response_received_at_utc"]),
                "interpretation": row["interpretation_action"],
                "sender": row["responder_address"],
            }
            for row in operations
        ]

        levels_reached = max((row["level"] for row in routings), default=0)

        resolution_snapshot = None
        if resolution is not None:
            resolution_snapshot = {
                "resolution_id": resolution["resolution_id"],
                "proposed_by": resolution["proposed_by"],
                "proposed_at": _iso(resolution["proposed_at_utc"]),
                "routing_id": resolution["routing_id"],
                "resolution_text": resolution["resolution_text"],
                "resolution_status": resolution["status"],
            }

        approval_snapshot = None
        if approval is not None:
            approval_snapshot = {
                "approval_id": approval["approval_id"],
                "approver": approval["decided_by"],
                "approver_level": approval["approver_level"],
                "decision": approval["status"],
                "decision_at": _iso(approval["decided_at_utc"]),
                "decision_reason": approval["decision_reason"],
                "source_message_id": approval["decision_source_external_message_id"],
            }

        metrics = compute_metrics(
            received_at=received_at,
            resolved_at=resolved_at,
            routing_count=len(routing_list),
            escalation_count=len(escalation_list),
            slas=sla_list,
            levels_reached=levels_reached,
        )
        timeline = build_timeline(
            received_at=received_at,
            confirmed_at=request["confirmed_at_utc"],
            routings=routing_list,
            slas=sla_list,
            escalations=escalation_list,
            resolution=resolution_snapshot,
            approval=approval_snapshot,
        )

        snapshot: dict[str, Any] = {
            "schema_version": AUDIT_SCHEMA_VERSION,
            "request": {
                "request_id": request["request_id"],
                "conversation_id": request["conversation_id"],
                "sector_id": sector["sector_id"] if sector else None,
                "sector_name": sector["display_name"] if sector else None,
                "category": request["category"],
                "description": request["description"],
                "location": request["location_text"],
                "citizen_address": request["citizen_address"],
                "origin_channel": request["origin_channel"],
                "received_at": _iso(received_at),
                "confirmed_at": _iso(request["confirmed_at_utc"]),
            },
            "routings": routing_list,
            "slas": sla_list,
            "escalations": escalation_list,
            "operations": operation_list,
            "resolution": resolution_snapshot,
            "approval": approval_snapshot,
            "result": {
                "request_status": request["status"],
                "resolved_at": _iso(resolved_at),
            },
            "metrics": metrics,
            "timeline": timeline,
        }
        return snapshot

    async def create_record(
        self,
        conn: AsyncConnection,
        *,
        request_id: str,
        schema_version: int,
        resolved_at: datetime,
        snapshot: dict[str, Any],
        snapshot_sha256: str,
    ) -> str:
        from psycopg.types.json import Jsonb

        row = await fetch_one(
            conn,
            """
            insert into flow_case_audit_records (
                request_id, schema_version, resolved_at_utc,
                snapshot_jsonb, snapshot_sha256
            ) values (
                %(request_id)s, %(schema_version)s, %(resolved_at)s,
                %(snapshot)s, %(snapshot_sha256)s
            )
            on conflict (request_id, schema_version) do nothing
            returning id::text
            """,
            {
                "request_id": request_id,
                "schema_version": schema_version,
                "resolved_at": resolved_at,
                "snapshot": Jsonb(snapshot),
                "snapshot_sha256": snapshot_sha256,
            },
        )
        if row is not None:
            return row["id"]
        existing = await fetch_one(
            conn,
            """
            select id::text
            from flow_case_audit_records
            where request_id = %(request_id)s
              and schema_version = %(schema_version)s
            """,
            {"request_id": request_id, "schema_version": schema_version},
        )
        if existing is None:
            raise RuntimeError("Flow audit record conflict returned no row.")
        return existing["id"]

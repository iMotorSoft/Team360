"""Repeatable LaMuni end-to-end Flow demo.

Runs one full controlled scenario against the real Flow services and real
PostgreSQL:

    intake -> classification -> confirmation -> N1 routing -> SLA breach ->
    N2 escalation -> technical operational reply -> resolution proposal ->
    supervisor APPROVE -> RESOLVED -> audit snapshot -> executive list/detail.

Transport (messaging and LLM) is deterministic; the domain services are the
same code paths used by production. Every run creates a brand new case with a
unique LAMUNI marker. Nothing is daemonized and no SQL updates business state.

Usage:

    uv run python -m modules.flow.demo.run

    uv run python -m modules.flow.demo.run --status <request_id>

The full scenario requires the applied Flow migrations and a reachable
PostgreSQL. Set TEAM360_FLOW_LAMUNI_DEMO=1 to force the real PostgreSQL test
path in the test suite.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from modules.db.pool import close_pool, create_pool, open_pool
from modules.db.settings import get_database_settings
from modules.messaging.domain import InboundMessage

from ..audit_repository import FlowAuditRepository
from ..automatic_runner import FlowAutomaticRunner
from ..closure_repository import FlowClosurePostgresRepository
from ..closure_service import FlowClosureService
from ..configuration_service import FlowConfigurationService
from ..domain import ApprovalDecision
from ..escalation_repository import FlowEscalationPostgresRepository
from ..executive_list_service import FlowExecutiveListService
from ..executive_service import FlowExecutiveAuditService
from ..operational_repository import FlowOperationalPostgresRepository
from ..operational_service import FlowOperationalReplyService
from ..repository import FlowPostgresRepository
from ..routing_repository import FlowRoutingPostgresRepository
from ..routing_service import FlowRoutingService
from ..service import FlowIntakeService
from ..sla_repository import FlowSLARepository
from .transport import (
    DemoApprovalInterpreter,
    DemoIntakeInterpreter,
    DemoOperationalInterpreter,
    DemoReplySender,
    DemoRoutingSender,
)

CITIZEN = "vecino@example.com"
TECHNICIAN = "tecnico@alquimiablue.com"
DEMO_DESCRIPTION = "Poste de alumbrado con falla de conexion en el corredor"
DEMO_LOCATION = "Avenida de los Eucaliptos 980, boulevard norte"


@dataclass(frozen=True, slots=True)
class DemoReport:
    marker: str
    request_id: str
    conversation_id: str
    classification: str
    sector_id: str
    n1_routing_id: str
    n1_destination: str
    n1_sla_id: str
    n1_sla_status: str
    n1_due_at: str
    escalation_id: str
    n2_routing_id: str
    n2_destination: str
    resolution_id: str
    approval_id: str
    approver_level: int | None
    approver_destination: str
    final_status: str
    resolution_status: str
    approval_status: str
    audit_id: str | None
    audit_schema_version: int | None
    audit_hash: str | None
    directorio_visible: bool
    directorio_data_source: str
    directorio_status_fact: str
    configuration: dict = field(default_factory=dict)

    def summary_lines(self) -> list[str]:
        return [
            "LAMUNI_DEMO_REPORT",
            f"DEMO_ID={self.marker}",
            f"REQUEST_ID={self.request_id}",
            f"SECTOR={self.sector_id}",
            f"CATEGORY={self.classification}",
            f"N1_ROUTING={self.n1_routing_id}",
            f"N1_SLA={self.n1_sla_status}",
            f"ESCALATION={self.escalation_id}",
            f"N2_ROUTING={self.n2_routing_id}",
            f"RESOLUTION={self.resolution_id}",
            f"APPROVAL={self.approval_id}",
            f"FINAL_STATUS={self.final_status}",
            f"AUDIT_ID={self.audit_id}",
            f"DIRECTORIO_VISIBLE={self.directorio_visible}",
        ]


async def _fetch_one(pool_settings, query: str, params: dict) -> dict | None:
    async with await psycopg.AsyncConnection.connect(
        pool_settings.dsn, row_factory=dict_row
    ) as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params)
            return await cur.fetchone()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _message(
    *,
    message_id: str,
    thread_id: str,
    sender: str,
    subject: str,
    body: str,
    received_at: datetime,
    in_reply_to: str = "",
    references: str = "",
    rfc_message_id: str = "",
) -> InboundMessage:
    metadata = {}
    if in_reply_to:
        metadata["in_reply_to"] = in_reply_to
    if references:
        metadata["references"] = references
    if rfc_message_id:
        metadata["rfc_message_id"] = rfc_message_id
    return InboundMessage(
        provider="gmail",
        channel="email",
        external_message_id=message_id,
        external_thread_id=thread_id,
        sender=sender,
        recipients=("mesaentrada@alquimiablue.com",),
        subject=subject,
        text_body=body,
        received_at=received_at,
        metadata=metadata,
    )


async def run_demo(pool, settings) -> DemoReport:
    marker = f"LAMUNI-DEMO-{datetime.now(timezone.utc):%Y%m%d}-{uuid4().hex[:6]}"
    thread = f"lamuni-demo-{uuid4().hex}"
    now = _now()

    reply_sender = DemoReplySender()
    routing_sender = DemoRoutingSender()
    intake = DemoIntakeInterpreter(DEMO_DESCRIPTION, DEMO_LOCATION, marker)

    intake_service = FlowIntakeService(
        pool=pool,
        repository=FlowPostgresRepository(),
        interpreter=intake,
        reply_sender=reply_sender,
    )
    closure_service = FlowClosureService(
        pool=pool,
        repository=FlowClosurePostgresRepository(),
        audit_repository=FlowAuditRepository(),
        interpreter=DemoApprovalInterpreter(),
        sender=routing_sender,
    )
    operational_service = FlowOperationalReplyService(
        pool=pool,
        repository=FlowOperationalPostgresRepository(),
        interpreter=DemoOperationalInterpreter(),
        closure=closure_service,
    )

    # 1. Intake: citizen message -> interpreted -> pending confirmation.
    initial = _message(
        message_id=f"{marker}-m1",
        thread_id=thread,
        sender=CITIZEN,
        subject="Solicitud de alumbrado publico",
        body=f"{DEMO_DESCRIPTION} {marker}.",
        received_at=now,
        rfc_message_id=f"<citizen-{marker}-m1@example.com>",
    )
    first = await intake_service.process(initial)
    if not first.processed or not first.candidate_count:
        raise RuntimeError("DEMO_INTAKE_FAILURE")

    # 2. Confirmation.
    confirm = _message(
        message_id=f"{marker}-m2",
        thread_id=thread,
        sender=CITIZEN,
        subject="Re: Solicitud de alumbrado publico",
        body="Si, correcto.",
        received_at=now,
        in_reply_to=f"<citizen-{marker}-m1@example.com>",
    )
    confirmed = await intake_service.process(confirm)
    if not confirmed.processed or confirmed.confirmed_count != 1:
        raise RuntimeError("DEMO_CONFIRMATION_FAILURE")

    request_row = await _fetch_one(
        settings,
        """
        select fr.id::text as request_id, fr.conversation_id::text as conversation_id,
               fr.tentative_category, fr.status
        from flow_requests fr
        join flow_conversations fc on fc.id = fr.conversation_id
        where fc.external_thread_id = %(thread)s
        """,
        {"thread": thread},
    )
    if request_row is None or request_row["status"] != "CONFIRMED":
        raise RuntimeError("DEMO_ROUTING_FAILURE")
    request_id = request_row["request_id"]
    conversation_id = request_row["conversation_id"]

    # 3. Routing N1 (real send through the deterministic routing sender).
    routing_service = FlowRoutingService(
        pool=pool,
        repository=FlowRoutingPostgresRepository(),
        sender=routing_sender,
    )
    routed = await routing_service.route_confirmed_request(
        request_id, confirm_send=True
    )
    if routed.status != "ASSIGNED" or routed.assignment is None:
        raise RuntimeError("DEMO_ROUTING_FAILURE")
    n1_routing_id = routed.assignment.id
    n1_destination = routed.assignment.destination or ""

    sla_row = await _fetch_one(
        settings,
        """
        select fs.id::text, fs.status, fs.due_at_utc
        from flow_request_slas fs
        where fs.routing_id = %(routing_id)s
        order by fs.started_at_utc desc
        limit 1
        """,
        {"routing_id": n1_routing_id},
    )
    if sla_row is None:
        raise RuntimeError("DEMO_SLA_FAILURE")
    n1_sla_id = sla_row["id"]
    n1_due_at = sla_row["due_at_utc"]

    # 4. SLA + automatic escalation using an injected clock past the deadline.
    future = n1_due_at + timedelta(seconds=1)
    runner = FlowAutomaticRunner(
        pool=pool,
        sla_repository=FlowSLARepository(),
        escalation_repository=FlowEscalationPostgresRepository(),
        routing_repository=FlowRoutingPostgresRepository(),
        sender=routing_sender,
        clock=lambda: future,
    )
    summary = await runner.run_once(confirm_send=True)
    if summary.breached < 1 or summary.completed < 1:
        raise RuntimeError("DEMO_ESCALATION_FAILURE")

    n2_row = await _fetch_one(
        settings,
        """
        select frr.id::text, frr.destination,
               frr.outbound_observed_rfc_message_id,
               frr.outbound_rfc_message_id
        from flow_request_routings frr
        where frr.request_id = %(request_id)s
          and frr.routing_key = 'alumbrado_level_2'
        """,
        {"request_id": request_id},
    )
    if n2_row is None:
        raise RuntimeError("DEMO_ESCALATION_FAILURE")
    n2_routing_id = n2_row["id"]
    n2_destination = n2_row["destination"]
    n2_rfc = n2_row["outbound_observed_rfc_message_id"] or n2_row[
        "outbound_rfc_message_id"
    ]

    escalation_row = await _fetch_one(
        settings,
        """
        select fe.id::text
        from flow_request_escalations fe
        where fe.request_id = %(request_id)s
        order by fe.created_at_utc desc
        limit 1
        """,
        {"request_id": request_id},
    )
    escalation_id = escalation_row["id"] if escalation_row else ""

    # 5. Operational technical reply on N2 -> resolution proposal.
    technical = _message(
        message_id=f"{marker}-m3",
        thread_id=f"operational-{uuid4().hex}",
        sender=TECHNICIAN,
        subject=f"Re: {request_id}",
        body="Reparacion realizada. La luminaria quedo operativa.",
        received_at=future,
        in_reply_to=n2_rfc or "",
    )
    operational = await operational_service.process_if_operational(technical)
    if not operational.processed or operational.proposal is None:
        raise RuntimeError("DEMO_OPERATIONAL_REPLY_FAILURE")
    if operational.proposal.approval_id is None:
        raise RuntimeError("DEMO_RESOLUTION_FAILURE")
    resolution_id = operational.proposal.resolution_id or ""
    approval_id = operational.proposal.approval_id
    approver_level = operational.proposal.approver_level
    approver_destination = operational.proposal.approver_destination or ""

    approval_row = await _fetch_one(
        settings,
        """
        select fca.approval_token, fca.outbound_observed_rfc_message_id,
               fca.outbound_rfc_message_id
        from flow_closure_approvals fca
        where fca.id = %(approval_id)s
        """,
        {"approval_id": approval_id},
    )
    if approval_row is None:
        raise RuntimeError("DEMO_APPROVAL_FAILURE")
    approval_token = approval_row["approval_token"]
    approval_rfc = (
        approval_row["outbound_observed_rfc_message_id"]
        or approval_row["outbound_rfc_message_id"]
    )

    # 6. Supervisor APPROVE -> RESOLVED + audit snapshot.
    decision = _message(
        message_id=f"{marker}-m4",
        thread_id=f"approval-{uuid4().hex}",
        sender=approver_destination or TECHNICIAN,
        subject=(
            f"Re: [Team360 Flow][CIERRE][R:{approval_token}][{request_id}] "
            "Aprobacion de cierre"
        ),
        body="APROBAR",
        received_at=future + timedelta(seconds=1),
        in_reply_to=approval_rfc or "",
    )
    approval_result = await closure_service.process_approval_reply(decision)
    if approval_result.decision != ApprovalDecision.APPROVE:
        raise RuntimeError("DEMO_APPROVAL_FAILURE")

    # 7. Audit + executive verification.
    executive = FlowExecutiveAuditService(
        pool=pool,
        closure_repository=FlowClosurePostgresRepository(),
        audit_repository=FlowAuditRepository(),
    )
    view = await executive.query_case(request_id)
    view_again = await executive.query_case(request_id)
    audit_id = (view.get("audit") or {}).get("audit_record_id")
    audit_hash = (view.get("audit") or {}).get("snapshot_sha256")
    schema_version = (view.get("audit") or {}).get("schema_version")
    if view["status_fact"] != "closed" or view["data_source"] != "AUDIT_SNAPSHOT":
        raise RuntimeError("DEMO_EXECUTIVE_DETAIL_FAILURE")
    if audit_id is None or view_again["audit"].get("audit_record_id") != audit_id:
        raise RuntimeError("DEMO_AUDIT_FAILURE")
    if view_again["audit"].get("snapshot_sha256") != audit_hash:
        raise RuntimeError("DEMO_AUDIT_FAILURE")

    listed = await FlowExecutiveListService(pool=pool).list_cases(
        search=marker, page_size=20
    )
    found = [
        item for item in listed["items"] if item["request_id"] == request_id
    ]
    if not found:
        raise RuntimeError("DEMO_EXECUTIVE_LIST_FAILURE")
    item = found[0]

    configuration = await FlowConfigurationService(pool=pool).get_configuration(
        "alumbrado"
    )

    report = DemoReport(
        marker=marker,
        request_id=request_id,
        conversation_id=conversation_id,
        classification=request_row["tentative_category"] or "",
        sector_id="alumbrado",
        n1_routing_id=n1_routing_id,
        n1_destination=n1_destination,
        n1_sla_id=n1_sla_id,
        n1_sla_status=summary.breached and "BREACHED" or "PENDING",
        n1_due_at=n1_due_at.isoformat(),
        escalation_id=escalation_id,
        n2_routing_id=n2_routing_id,
        n2_destination=n2_destination,
        resolution_id=resolution_id,
        approval_id=approval_id,
        approver_level=approver_level,
        approver_destination=approver_destination,
        final_status=view["status"],
        resolution_status="APPROVED",
        approval_status="APPROVED",
        audit_id=audit_id,
        audit_schema_version=schema_version,
        audit_hash=(audit_hash or "")[:16],
        directorio_visible=True,
        directorio_data_source=item["data_source"],
        directorio_status_fact=item["status_fact"],
        configuration=configuration or {},
    )
    return report


async def _status(pool, settings, request_id: str) -> dict:
    executive = FlowExecutiveAuditService(
        pool=pool,
        closure_repository=FlowClosurePostgresRepository(),
        audit_repository=FlowAuditRepository(),
    )
    view = await executive.query_case(request_id)
    return {
        "request_id": request_id,
        "status": view["status"],
        "status_fact": view["status_fact"],
        "data_source": view["data_source"],
        "audit_record_id": (view.get("audit") or {}).get("audit_record_id"),
        "snapshot_sha256": (view.get("audit") or {}).get("snapshot_sha256"),
    }


async def cleanup_demo_cases(pool) -> int:
    """Delete only the LAMUNI demo cases created by this harness.

    Identified by the ``lamuni-demo-`` conversation thread prefix. This keeps
    the DEV database stable for the existing LIVE E2E regression without
    touching any other Flow case. Returns the number of conversations removed.
    """
    async with pool.connection() as conn:
        async with conn.transaction():
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    select count(*) from flow_conversations
                    where external_thread_id like 'lamuni-demo-%'
                    """
                )
                count = (await cur.fetchone())["count"]
                # The resolution guard trigger blocks mutating RESOLVED rows and
                # the approvals<->requests FK cycle is NOACTION, so the trigger
                # is disabled for the duration of this single transaction and
                # restored before commit (a rollback restores it too). The
                # transient CONFIRMED status satisfies the resolution-evidence
                # CHECK while the FK reference is removed; the rows are deleted
                # in the same transaction.
                await cur.execute(
                    "alter table flow_requests "
                    "disable trigger trg_flow_request_resolution_guard"
                )
                await cur.execute(
                    """
                    update flow_requests
                    set status = 'CONFIRMED', authorized_approval_id = null
                    where conversation_id in (
                        select fc.id from flow_conversations fc
                        where fc.external_thread_id like 'lamuni-demo-%'
                    )
                    """
                )
                await cur.execute(
                    """
                    delete from flow_case_audit_records
                    where request_id in (
                        select fr.id from flow_requests fr
                        join flow_conversations fc on fc.id = fr.conversation_id
                        where fc.external_thread_id like 'lamuni-demo-%'
                    )
                    """
                )
                await cur.execute(
                    """
                    delete from flow_closure_approvals
                    where request_id in (
                        select fr.id from flow_requests fr
                        join flow_conversations fc on fc.id = fr.conversation_id
                        where fc.external_thread_id like 'lamuni-demo-%'
                    )
                    """
                )
                await cur.execute(
                    """
                    delete from flow_request_resolutions
                    where request_id in (
                        select fr.id from flow_requests fr
                        join flow_conversations fc on fc.id = fr.conversation_id
                        where fc.external_thread_id like 'lamuni-demo-%'
                    )
                    """
                )
                await cur.execute(
                    """
                    delete from flow_request_escalations
                    where request_id in (
                        select fr.id from flow_requests fr
                        join flow_conversations fc on fc.id = fr.conversation_id
                        where fc.external_thread_id like 'lamuni-demo-%'
                    )
                    """
                )
                await cur.execute(
                    """
                    delete from flow_request_operational_events
                    where request_id in (
                        select fr.id from flow_requests fr
                        join flow_conversations fc on fc.id = fr.conversation_id
                        where fc.external_thread_id like 'lamuni-demo-%'
                    )
                    """
                )
                await cur.execute(
                    """
                    delete from flow_request_sla_events
                    where sla_id in (
                        select fs.id from flow_request_slas fs
                        join flow_requests fr on fr.id = fs.request_id
                        join flow_conversations fc on fc.id = fr.conversation_id
                        where fc.external_thread_id like 'lamuni-demo-%'
                    )
                    """
                )
                await cur.execute(
                    """
                    delete from flow_request_slas
                    where request_id in (
                        select fr.id from flow_requests fr
                        join flow_conversations fc on fc.id = fr.conversation_id
                        where fc.external_thread_id like 'lamuni-demo-%'
                    )
                    """
                )
                await cur.execute(
                    """
                    delete from flow_request_work_states
                    where routing_id in (
                        select frr.id from flow_request_routings frr
                        join flow_requests fr on fr.id = frr.request_id
                        join flow_conversations fc on fc.id = fr.conversation_id
                        where fc.external_thread_id like 'lamuni-demo-%'
                    )
                    """
                )
                await cur.execute(
                    """
                    delete from flow_request_routings
                    where request_id in (
                        select fr.id from flow_requests fr
                        join flow_conversations fc on fc.id = fr.conversation_id
                        where fc.external_thread_id like 'lamuni-demo-%'
                    )
                    """
                )
                await cur.execute(
                    """
                    delete from flow_requests
                    where conversation_id in (
                        select fc.id from flow_conversations fc
                        where fc.external_thread_id like 'lamuni-demo-%'
                    )
                    """
                )
                await cur.execute(
                    """
                    delete from flow_request_candidates
                    where conversation_id in (
                        select fc.id from flow_conversations fc
                        where fc.external_thread_id like 'lamuni-demo-%'
                    )
                    """
                )
                await cur.execute(
                    """
                    delete from flow_interpretations
                    where conversation_id in (
                        select fc.id from flow_conversations fc
                        where fc.external_thread_id like 'lamuni-demo-%'
                    )
                    """
                )
                await cur.execute(
                    """
                    delete from flow_messages
                    where conversation_id in (
                        select fc.id from flow_conversations fc
                        where fc.external_thread_id like 'lamuni-demo-%'
                    )
                    """
                )
                await cur.execute(
                    """
                    delete from flow_conversations
                    where external_thread_id like 'lamuni-demo-%'
                    """
                )
                await cur.execute(
                    "alter table flow_requests "
                    "enable trigger trg_flow_request_resolution_guard"
                )
                return int(count)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Team360 Flow LaMuni repeatable end-to-end demo."
    )
    parser.add_argument(
        "--status",
        metavar="REQUEST_ID",
        help="Print the executive status of an existing case and exit.",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Delete only the LAMUNI demo cases created by this harness.",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()

    async def _run() -> int:
        settings = get_database_settings(min_size=1, max_size=4)
        pool = create_pool(settings)
        await open_pool(pool)
        try:
            if args.cleanup:
                removed = await cleanup_demo_cases(pool)
                print(f"LAMUNI_DEMO_CLEANUP removed_conversations={removed}")
                return 0
            if args.status:
                status = await _status(pool, settings, args.status)
                print(
                    "LAMUNI_DEMO_STATUS "
                    + " ".join(f"{k}={v}" for k, v in status.items())
                )
                return 0
            report = await run_demo(pool, settings)
            print("\n".join(report.summary_lines()))
            print(f"CONFIGURATION_SECTOR={report.configuration.get('sector_id')}")
            print(
                "CONFIGURATION_CLOSURE_LEVEL="
                f"{report.configuration.get('closure_approval_level')}"
            )
            return 0
        finally:
            await close_pool(pool)

    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
